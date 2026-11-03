"""Client accounts (companies, agencies, NGOs) and the people at them."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from ..audit import audit
from ..db import get_conn
from ..deps import current_user, require
from ..errors import Problem
from ..schemas import AccountDetail, AccountIn, AccountOut, AccountPatch, ContactIn, ContactOut, ContactPatch
from .activities import ACTIVITY_SQL
from .deals import DEAL_SQL
from .invoices import INVOICE_SQL, _shape

router = APIRouter(tags=["accounts"])

ACCOUNT_SQL = (
    "SELECT a.*, u.name AS owner_name, "
    "  (SELECT count(*) FROM deals d WHERE d.account_id = a.id AND d.stage NOT IN ('won','lost')) AS open_deals, "
    "  (SELECT COALESCE(sum(d.amount_ngn), 0) FROM deals d WHERE d.account_id = a.id AND d.stage NOT IN ('won','lost')) AS open_value_ngn, "
    "  (SELECT c.name FROM contacts c WHERE c.account_id = a.id ORDER BY c.is_primary DESC, c.created_at LIMIT 1) AS primary_contact "
    "FROM accounts a LEFT JOIN users u ON u.id = a.owner_id ")


async def _owner_ok(conn, owner_id) -> None:
    if owner_id:
        cur = await conn.execute("SELECT 1 FROM users WHERE id = %s AND active", (owner_id,))
        if not await cur.fetchone():
            raise Problem(422, "Choose an active staff member.", code="validation", fields={"owner_id": ["not staff"]})


async def _account(conn, account_id) -> dict:
    cur = await conn.execute(ACCOUNT_SQL + "WHERE a.id = %s", (account_id,))
    a = await cur.fetchone()
    if not a:
        raise Problem(404, "Client not found.", code="not_found")
    return a


@router.get("/accounts", response_model=list[AccountOut], summary="Clients, newest change first")
async def list_accounts(q: str | None = None, status: str | None = Query(None, pattern="^(lead|customer|former)$"),
                        owner_id: UUID | None = None, limit: int = Query(200, ge=1, le=500),
                        user=Depends(current_user), conn=Depends(get_conn)):
    where, params = ["true"], []
    if q:
        where.append("(a.name ILIKE %s OR a.email ILIKE %s OR a.city ILIKE %s OR EXISTS (SELECT 1 FROM contacts c "
                     "WHERE c.account_id = a.id AND (c.name ILIKE %s OR c.email ILIKE %s)))")
        params += [f"%{q}%"] * 5
    if status:
        where.append("a.status = %s"); params.append(status)
    if owner_id:
        where.append("a.owner_id = %s"); params.append(owner_id)
    cur = await conn.execute(ACCOUNT_SQL + f"WHERE {' AND '.join(where)} ORDER BY a.updated_at DESC LIMIT %s", (*params, limit))
    return await cur.fetchall()


@router.post("/accounts", response_model=AccountOut, status_code=201)
async def create_account(body: AccountIn, user=Depends(require("accounts.edit")), conn=Depends(get_conn)):
    await _owner_ok(conn, body.owner_id)
    data = body.model_dump()
    data["owner_id"] = data["owner_id"] or user["id"]
    data["name"] = data["name"].strip()
    cols = list(data)
    cur = await conn.execute(f"INSERT INTO accounts ({', '.join(cols)}, created_by) VALUES ({', '.join(['%s'] * len(cols))}, %s) "
                             "RETURNING id", (*data.values(), user["id"]))
    aid = (await cur.fetchone())["id"]
    await audit(conn, "account.create", actor_id=user["id"], target_type="account", target_id=aid, name=data["name"])
    return await _account(conn, aid)


@router.get("/accounts/{account_id}", response_model=AccountDetail, summary="A client with its contacts, deals and activity")
async def get_account(account_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    a = await _account(conn, account_id)
    cur = await conn.execute("SELECT * FROM contacts WHERE account_id = %s ORDER BY is_primary DESC, lower(name)", (account_id,))
    contacts = await cur.fetchall()
    cur = await conn.execute(DEAL_SQL + "WHERE d.account_id = %s ORDER BY d.closed_at NULLS FIRST, d.updated_at DESC", (account_id,))
    deals = await cur.fetchall()
    cur = await conn.execute(ACTIVITY_SQL + "WHERE x.account_id = %s OR x.deal_id IN (SELECT id FROM deals WHERE account_id = %s) "
                             "ORDER BY (x.done_at IS NULL AND x.kind = 'task') DESC, COALESCE(x.done_at, x.due_at, x.created_at) DESC LIMIT 200",
                             (account_id, account_id))
    activities = await cur.fetchall()
    cur = await conn.execute(INVOICE_SQL + "WHERE i.account_id = %s ORDER BY (i.status = 'draft') DESC, i.issue_date DESC NULLS LAST, "
                             "i.created_at DESC", (account_id,))
    invoices = [_shape(r) for r in await cur.fetchall()]
    return {**a, "contacts": contacts, "deals": deals, "activities": activities, "invoices": invoices}


@router.patch("/accounts/{account_id}", response_model=AccountOut)
async def update_account(account_id: UUID, body: AccountPatch, user=Depends(require("accounts.edit")), conn=Depends(get_conn)):
    await _account(conn, account_id)
    data = body.model_dump(exclude_unset=True)
    if "owner_id" in data:
        await _owner_ok(conn, data["owner_id"])
    if data:
        sets = ", ".join(f"{k} = %s" for k in data)
        await conn.execute(f"UPDATE accounts SET {sets}, updated_at = now() WHERE id = %s", (*data.values(), account_id))
        await audit(conn, "account.update", actor_id=user["id"], target_type="account", target_id=account_id,
                    **body.model_dump(exclude_unset=True, mode="json"))
    return await _account(conn, account_id)


@router.delete("/accounts/{account_id}", status_code=204, summary="Delete a client with its contacts, deals and activity (super admins)")
async def delete_account(account_id: UUID, user=Depends(require("records.delete")), conn=Depends(get_conn)):
    a = await _account(conn, account_id)
    cur = await conn.execute("SELECT count(*) AS n FROM invoices WHERE account_id = %s AND status <> 'draft'", (account_id,))
    if (await cur.fetchone())["n"]:
        raise Problem(409, "This client has issued invoices, which are kept for the records. Mark it as a former client instead.",
                      code="has_invoices")
    await conn.execute("DELETE FROM invoices WHERE account_id = %s", (account_id,))
    await conn.execute("DELETE FROM accounts WHERE id = %s", (account_id,))
    await audit(conn, "account.delete", actor_id=user["id"], target_type="account", target_id=account_id, name=a["name"])
    return Response(status_code=204)


# ---------- contacts ----------
async def _touch(conn, account_id) -> None:
    await conn.execute("UPDATE accounts SET updated_at = now() WHERE id = %s", (account_id,))


@router.post("/accounts/{account_id}/contacts", response_model=ContactOut, status_code=201)
async def add_contact(account_id: UUID, body: ContactIn, user=Depends(require("contacts.edit")), conn=Depends(get_conn)):
    await _account(conn, account_id)
    if body.is_primary:
        await conn.execute("UPDATE contacts SET is_primary = false WHERE account_id = %s", (account_id,))
    cur = await conn.execute("INSERT INTO contacts (account_id, name, title, email, phone, is_primary, notes) "
                             "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *",
                             (account_id, body.name.strip(), body.title, body.email.strip().lower(), body.phone, body.is_primary, body.notes))
    c = await cur.fetchone()
    await _touch(conn, account_id)
    await audit(conn, "contact.create", actor_id=user["id"], target_type="contact", target_id=c["id"], account_id=str(account_id))
    return c


@router.patch("/contacts/{contact_id}", response_model=ContactOut)
async def update_contact(contact_id: UUID, body: ContactPatch, user=Depends(require("contacts.edit")), conn=Depends(get_conn)):
    cur = await conn.execute("SELECT account_id FROM contacts WHERE id = %s", (contact_id,))
    c = await cur.fetchone()
    if not c:
        raise Problem(404, "Contact not found.", code="not_found")
    data = body.model_dump(exclude_unset=True)
    if data.get("is_primary"):
        await conn.execute("UPDATE contacts SET is_primary = false WHERE account_id = %s", (c["account_id"],))
    if "email" in data and data["email"] is not None:
        data["email"] = data["email"].strip().lower()
    if data:
        await conn.execute(f"UPDATE contacts SET {', '.join(f'{k} = %s' for k in data)} WHERE id = %s", (*data.values(), contact_id))
        await _touch(conn, c["account_id"])
        await audit(conn, "contact.update", actor_id=user["id"], target_type="contact", target_id=contact_id)
    cur = await conn.execute("SELECT * FROM contacts WHERE id = %s", (contact_id,))
    return await cur.fetchone()


@router.delete("/contacts/{contact_id}", status_code=204)
async def delete_contact(contact_id: UUID, user=Depends(require("contacts.edit")), conn=Depends(get_conn)):
    cur = await conn.execute("DELETE FROM contacts WHERE id = %s RETURNING account_id, name", (contact_id,))
    c = await cur.fetchone()
    if not c:
        raise Problem(404, "Contact not found.", code="not_found")
    await _touch(conn, c["account_id"])
    await audit(conn, "contact.delete", actor_id=user["id"], target_type="contact", target_id=contact_id, name=c["name"])
    return Response(status_code=204)
