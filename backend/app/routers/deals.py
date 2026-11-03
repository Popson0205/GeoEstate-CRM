"""The sales pipeline: each deal moves New -> Contacted -> Demo -> Proposal -> Won or Lost. Amounts are in naira,
before VAT. A won deal turns its client into a customer."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from ..audit import audit
from ..db import get_conn
from ..deps import current_user, require
from ..errors import Problem
from ..schemas import DealIn, DealOut, DealPatch

router = APIRouter(tags=["deals"])
DEAL_SQL = ("SELECT d.*, a.name AS account_name, u.name AS owner_name FROM deals d JOIN accounts a ON a.id = d.account_id "
            "LEFT JOIN users u ON u.id = d.owner_id ")
CLOSED = ("won", "lost")


async def _deal(conn, deal_id) -> dict:
    cur = await conn.execute(DEAL_SQL + "WHERE d.id = %s", (deal_id,))
    d = await cur.fetchone()
    if not d:
        raise Problem(404, "Deal not found.", code="not_found")
    return d


async def _owner_ok(conn, owner_id) -> None:
    if owner_id:
        cur = await conn.execute("SELECT 1 FROM users WHERE id = %s AND active", (owner_id,))
        if not await cur.fetchone():
            raise Problem(422, "Choose an active staff member.", code="validation", fields={"owner_id": ["not staff"]})


async def _won(conn, account_id) -> None:
    await conn.execute("UPDATE accounts SET status = 'customer', updated_at = now() WHERE id = %s AND status <> 'customer'", (account_id,))


@router.get("/deals", response_model=list[DealOut], summary="Deals, for the pipeline board")
async def list_deals(stage: str | None = Query(None, pattern="^(new|contacted|demo|proposal|won|lost|open)$"),
                     owner_id: UUID | None = None, q: str | None = None,
                     closed_days: int = Query(90, ge=0, le=3650, description="Won and lost deals closed within this many days"),
                     user=Depends(current_user), conn=Depends(get_conn)):
    where, params = ["(d.stage NOT IN ('won','lost') OR d.closed_at > now() - make_interval(days => %s))"], [closed_days]
    if stage == "open":
        where.append("d.stage NOT IN ('won','lost')")
    elif stage:
        where.append("d.stage = %s"); params.append(stage)
    if owner_id:
        where.append("d.owner_id = %s"); params.append(owner_id)
    if q:
        where.append("(d.title ILIKE %s OR a.name ILIKE %s)"); params += [f"%{q}%"] * 2
    cur = await conn.execute(DEAL_SQL + f"WHERE {' AND '.join(where)} ORDER BY d.updated_at DESC LIMIT 1000", params)
    return await cur.fetchall()


@router.post("/deals", response_model=DealOut, status_code=201)
async def create_deal(body: DealIn, user=Depends(require("deals.edit")), conn=Depends(get_conn)):
    cur = await conn.execute("SELECT 1 FROM accounts WHERE id = %s", (body.account_id,))
    if not await cur.fetchone():
        raise Problem(422, "Choose a client for the deal.", code="validation", fields={"account_id": ["not found"]})
    await _owner_ok(conn, body.owner_id)
    if body.stage == "lost":
        raise Problem(422, "A new deal cannot start as lost.", code="validation", fields={"stage": ["lost"]})
    cur = await conn.execute(
        "INSERT INTO deals (account_id, title, plan, amount_ngn, stage, owner_id, expected_close, notes, created_by, closed_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CASE WHEN %s = 'won' THEN now() END) RETURNING id",
        (body.account_id, body.title.strip(), body.plan, body.amount_ngn, body.stage, body.owner_id or user["id"],
         body.expected_close, body.notes, user["id"], body.stage))
    did = (await cur.fetchone())["id"]
    if body.stage == "won":
        await _won(conn, body.account_id)
    await conn.execute("UPDATE accounts SET updated_at = now() WHERE id = %s", (body.account_id,))
    await audit(conn, "deal.create", actor_id=user["id"], target_type="deal", target_id=did, title=body.title.strip(), stage=body.stage)
    return await _deal(conn, did)


@router.get("/deals/{deal_id}", response_model=DealOut)
async def get_deal(deal_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    return await _deal(conn, deal_id)


@router.patch("/deals/{deal_id}", response_model=DealOut, summary="Change a deal, or move it along the pipeline")
async def update_deal(deal_id: UUID, body: DealPatch, user=Depends(require("deals.edit")), conn=Depends(get_conn)):
    d = await _deal(conn, deal_id)
    data = body.model_dump(exclude_unset=True, exclude={"clear_amount"})
    if body.clear_amount:
        data["amount_ngn"] = None
    if "owner_id" in data:
        await _owner_ok(conn, data["owner_id"])
    stage = data.get("stage")
    if stage == "lost" and not (data.get("lost_reason") or d["lost_reason"]).strip():
        raise Problem(422, "Say why the deal was lost: it helps the next one.", code="validation", fields={"lost_reason": ["needed"]})
    sets, params = [f"{k} = %s" for k in data], list(data.values())
    if stage and stage != d["stage"]:
        sets.append("closed_at = %s")
        params.append(None)
        if stage in CLOSED:
            sets[-1] = "closed_at = now()"
            params.pop()
    if sets:
        await conn.execute(f"UPDATE deals SET {', '.join(sets)}, updated_at = now() WHERE id = %s", (*params, deal_id))
        if stage == "won":
            await _won(conn, d["account_id"])
        await conn.execute("UPDATE accounts SET updated_at = now() WHERE id = %s", (d["account_id"],))
        await audit(conn, "deal.move" if stage and stage != d["stage"] else "deal.update", actor_id=user["id"], target_type="deal",
                    target_id=deal_id, **({"from": d["stage"], "to": stage} if stage and stage != d["stage"] else {}),
                    title=d["title"])
    return await _deal(conn, deal_id)


@router.delete("/deals/{deal_id}", status_code=204, summary="Delete a deal (super admins)")
async def delete_deal(deal_id: UUID, user=Depends(require("records.delete")), conn=Depends(get_conn)):
    d = await _deal(conn, deal_id)
    await conn.execute("DELETE FROM deals WHERE id = %s", (deal_id,))
    await audit(conn, "deal.delete", actor_id=user["id"], target_type="deal", target_id=deal_id, title=d["title"])
    return Response(status_code=204)
