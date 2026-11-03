"""Geohub, seen from the CRM: its customers and website requests, linking a client to its organization, bringing
them into the CRM, and setting up a customer on Geohub (from a paid invoice, or a month's demo)."""
from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from .. import geohub, invoicing
from ..audit import audit
from ..config import settings
from ..db import get_conn
from ..deps import current_user, require
from ..errors import Problem
from ..schemas import (AccountGeohubOut, GeohubOrg, GeohubRequest, GeohubStatusOut, ImportIn, ImportOut, LinkIn, SetupIn)

router = APIRouter(tags=["geohub"])

REQUEST_PLANS = {"standard": "standard", "advanced": "advanced", "custom": "custom", "demo": "demo", "unsure": "other"}
REQUEST_PLAN_NAMES = {"standard": "Organization Standard", "advanced": "Organization Advanced", "custom": "Custom",
                      "demo": "a month's demo", "unsure": "not sure yet"}


async def _linked(conn, column: str) -> dict:
    cur = await conn.execute(f"SELECT id, name, {column} AS key FROM accounts WHERE {column} IS NOT NULL")
    return {str(r["key"]): r for r in await cur.fetchall()}


def _with_account(items: list[dict], linked: dict) -> list[dict]:
    for x in items:
        a = linked.get(str(x["id"]))
        x["crm_account_id"], x["crm_account_name"] = (a["id"], a["name"]) if a else (None, None)
    return items


async def _account(conn, account_id) -> dict:
    cur = await conn.execute("SELECT * FROM accounts WHERE id = %s", (account_id,))
    a = await cur.fetchone()
    if not a:
        raise Problem(404, "Client not found.", code="not_found")
    return a


@router.get("/geohub", response_model=GeohubStatusOut, summary="Whether the CRM is linked to Geohub")
async def status(user=Depends(current_user)):
    return {"linked": geohub.configured(), "url": settings.geohub_url}


@router.get("/geohub/orgs", response_model=list[GeohubOrg], summary="Geohub's customers, with the CRM client each is linked to")
async def orgs(q: str | None = None, user=Depends(current_user), conn=Depends(get_conn)):
    items = await geohub.must("GET", "/orgs", params={"q": q} if q else None)
    return _with_account(items, await _linked(conn, "geohub_org_id"))


@router.get("/geohub/requests", response_model=list[GeohubRequest], summary="Requests from the Geohub website")
async def requests(status: str | None = Query(None, pattern="^(new|contacted|set_up|declined)$"), user=Depends(current_user),
                   conn=Depends(get_conn)):
    items = await geohub.must("GET", "/requests", params={"status": status} if status else None)
    linked = await _linked(conn, "geohub_request_id")
    by_org = await _linked(conn, "geohub_org_id")
    for x in _with_account(items, linked):            # a request that became a customer shows that client
        if not x["crm_account_id"] and x["org_id"] and str(x["org_id"]) in by_org:
            a = by_org[str(x["org_id"])]
            x["crm_account_id"], x["crm_account_name"] = a["id"], a["name"]
    return items


@router.post("/geohub/import", response_model=ImportOut, summary="Bring Geohub customers and requests into the CRM as clients")
async def import_(body: ImportIn, user=Depends(require("geohub.link")), conn=Depends(get_conn)):
    added, skipped = [], 0
    if body.org_ids:
        found = await geohub.must("GET", "/orgs", params={"ids": ",".join(str(i) for i in body.org_ids)})
        linked = await _linked(conn, "geohub_org_id")
        for o in found:
            if str(o["id"]) in linked:
                skipped += 1
                continue
            status = "customer" if o["licence_kind"] == "paid" and o["status"] in ("active", "grace") else \
                     "former" if o["status"] in ("expired", "suspended") and o["licence_kind"] == "paid" else "lead"
            cur = await conn.execute(
                "INSERT INTO accounts (name, email, status, owner_id, geohub_org_id, notes, created_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (o["name"], o["owner_email"] or "", status, user["id"], o["id"],
                 f"Brought in from Geohub: {o['plan_name']}, {o['status_name'].lower()}"
                 + (f", until {invoicing.long_date(date.fromisoformat(o['subscription_ends']))}" if o["subscription_ends"] else "")
                 + ".", user["id"]))
            aid = (await cur.fetchone())["id"]
            if o["owner_name"] or o["owner_email"]:
                await conn.execute("INSERT INTO contacts (account_id, name, title, email, is_primary) VALUES (%s, %s, %s, %s, true)",
                                   (aid, o["owner_name"] or o["owner_email"], "Owner on Geohub", (o["owner_email"] or "").lower()))
            added.append(aid)
    if body.request_ids:
        wanted = {str(i) for i in body.request_ids}
        found = [r for r in await geohub.must("GET", "/requests") if str(r["id"]) in wanted]
        linked = await _linked(conn, "geohub_request_id")
        by_org = await _linked(conn, "geohub_org_id")
        for r in found:
            if str(r["id"]) in linked or (r["org_id"] and str(r["org_id"]) in by_org):
                skipped += 1
                continue
            details = "\n".join(x for x in (f"Asked for: {REQUEST_PLAN_NAMES.get(r['plan'], r['plan'])}",
                                            f"Team size: {r['team_size']}" if r["team_size"] else "",
                                            r["message"] or "") if x)
            cur = await conn.execute(
                "INSERT INTO accounts (name, email, phone, status, owner_id, geohub_request_id, geohub_org_id, notes, created_by) "
                "VALUES (%s, %s, %s, 'lead', %s, %s, %s, %s, %s) RETURNING id",
                (r["organization"], r["email"], r["phone"] or "", user["id"], r["id"], r["org_id"],
                 f"Website request of {r['created_at'][:10]}.\n{details}", user["id"]))
            aid = (await cur.fetchone())["id"]
            await conn.execute("INSERT INTO contacts (account_id, name, email, phone, is_primary) VALUES (%s, %s, %s, %s, true)",
                               (aid, r["contact_name"], r["email"].lower(), r["phone"] or ""))
            plan = REQUEST_PLANS.get(r["plan"], "other")
            cur = await conn.execute(
                "INSERT INTO deals (account_id, title, plan, stage, owner_id, notes, geohub_request_id, created_by) "
                "VALUES (%s, %s, %s, 'new', %s, %s, %s, %s) RETURNING id",
                (aid, "Demo licence" if plan == "demo" else f"Geohub {REQUEST_PLAN_NAMES.get(r['plan'], 'licence')}"
                 if plan in ("standard", "advanced") else "Geohub licence", plan, user["id"], details, r["id"], user["id"]))
            deal_id = (await cur.fetchone())["id"]
            await conn.execute(
                "INSERT INTO activities (kind, subject, due_at, owner_id, account_id, deal_id, created_by) "
                "VALUES ('task', %s, now() + interval '2 days', %s, %s, %s, %s)",
                (f"Contact {r['contact_name']} about their website request", user["id"], aid, deal_id, user["id"]))
            added.append(aid)
    if added:
        await audit(conn, "geohub.import", actor_id=user["id"], added=len(added), skipped=skipped)
    return {"added": len(added), "skipped": skipped, "accounts": added}


# ---------- one client ----------
@router.get("/accounts/{account_id}/geohub", response_model=AccountGeohubOut, summary="The client's organization on Geohub today")
async def account_geohub(account_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    a = await _account(conn, account_id)
    if not a["geohub_org_id"]:
        return {"org": None}
    try:
        return {"org": await geohub.call("GET", f"/orgs/{a['geohub_org_id']}")}
    except geohub.GeohubError as e:
        return {"org": None, "error": str(e)}


@router.put("/accounts/{account_id}/geohub", response_model=AccountGeohubOut, summary="Link the client to its Geohub organization")
async def link(account_id: UUID, body: LinkIn, user=Depends(require("geohub.link")), conn=Depends(get_conn)):
    a = await _account(conn, account_id)
    cur = await conn.execute("SELECT name FROM accounts WHERE geohub_org_id = %s AND id <> %s", (body.org_id, account_id))
    other = await cur.fetchone()
    if other:
        raise Problem(409, f"That organization is already linked to {other['name']} in the CRM.", code="already_linked")
    org = await geohub.must("GET", f"/orgs/{body.org_id}")
    await conn.execute("UPDATE accounts SET geohub_org_id = %s, updated_at = now() WHERE id = %s", (body.org_id, account_id))
    await audit(conn, "geohub.link", actor_id=user["id"], target_type="account", target_id=account_id, org=org["name"],
                **({"before": str(a["geohub_org_id"])} if a["geohub_org_id"] else {}))
    return {"org": org}


@router.delete("/accounts/{account_id}/geohub", status_code=204, summary="Unlink the client from Geohub (nothing changes on Geohub)")
async def unlink(account_id: UUID, user=Depends(require("geohub.link")), conn=Depends(get_conn)):
    a = await _account(conn, account_id)
    if a["geohub_org_id"]:
        await conn.execute("UPDATE accounts SET geohub_org_id = NULL, updated_at = now() WHERE id = %s", (account_id,))
        await audit(conn, "geohub.unlink", actor_id=user["id"], target_type="account", target_id=account_id)
    return Response(status_code=204)


@router.post("/accounts/{account_id}/geohub/setup", response_model=AccountGeohubOut, status_code=201,
             summary="Set the client up on Geohub: from a paid invoice, or a month's demo")
async def setup(account_id: UUID, body: SetupIn, user=Depends(require("geohub.link")), conn=Depends(get_conn)):
    a = await _account(conn, account_id)
    if a["geohub_org_id"]:
        raise Problem(409, "This client is already linked to an organization on Geohub.", code="already_linked")
    cur = await conn.execute("SELECT name, email FROM contacts WHERE id = %s AND account_id = %s", (body.contact_id, account_id))
    owner = await cur.fetchone()
    if not owner:
        raise Problem(422, "Choose one of this client's contacts.", code="validation", fields={"contact_id": ["not found"]})
    if not owner["email"]:
        raise Problem(422, f"{owner['name']} has no email. Add one: Geohub emails the owner a link to set a password.",
                      code="validation", fields={"contact_id": ["no email"]})
    payload = {"name": a["name"], "owner_name": owner["name"], "owner_email": owner["email"], "staff_name": user["name"],
               "licence_kind": body.kind}
    inv = None
    if body.kind == "paid":
        if not body.invoice_id:
            raise Problem(422, "Choose the paid invoice the licence comes from.", code="validation", fields={"invoice_id": ["missing"]})
        cur = await conn.execute("SELECT * FROM invoices WHERE id = %s AND account_id = %s", (body.invoice_id, account_id))
        inv = await cur.fetchone()
        if not inv or inv["status"] != "paid" or not inv["licence_plan"]:
            raise Problem(409, "That invoice is not paid, or has no licence on it.", code="not_paid")
        if inv["licence_product"] != "hub":
            raise Problem(409, f"Invoice {inv['number']} is for {invoicing.PRODUCTS[inv['licence_product']]}, which is added to an "
                               "organization that is already on Geohub. Set the organization up on Geohub first (a Geohub licence or "
                               "a demo), then switch this licence on from the invoice.", code="not_hub")
        payload |= {"plan": inv["licence_plan"], "subscription_starts": inv["licence_starts"].isoformat(),
                    "subscription_ends": inv["licence_ends"].isoformat(), "invoice_ref": inv["number"]}
    if a["geohub_request_id"]:
        payload["request_id"] = str(a["geohub_request_id"])
    org = await geohub.must("POST", "/orgs", json=payload)
    await conn.execute("UPDATE accounts SET geohub_org_id = %s, status = CASE WHEN %s THEN 'customer' ELSE status END, "
                       "updated_at = now() WHERE id = %s", (org["id"], body.kind == "paid", account_id))
    if inv:
        await conn.execute("UPDATE invoices SET licence_applied_at = now(), licence_error = NULL WHERE id = %s", (inv["id"],))
    else:
        await conn.execute("UPDATE deals SET stage = 'demo', updated_at = now() WHERE account_id = %s AND plan = 'demo' "
                           "AND stage IN ('new','contacted')", (account_id,))
        end = date.today() + timedelta(days=29)
        await conn.execute("INSERT INTO activities (kind, subject, due_at, owner_id, account_id, created_by) "
                           "VALUES ('task', %s, %s, %s, %s, %s)",
                           (f"Demo ends {invoicing.long_date(end)}: follow up with {owner['name']}", end - timedelta(days=7),
                            a["owner_id"] or user["id"], account_id, user["id"]))
    await audit(conn, "geohub.setup", actor_id=user["id"], target_type="account", target_id=account_id, kind=body.kind,
                org=org["name"], owner=owner["email"], **({"invoice": inv["number"]} if inv else {}))
    return {"org": org}
