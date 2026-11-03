"""Staff activities: tasks to do (with a due date and someone they are assigned to), and calls, meetings, emails and
notes logged on a client or a deal."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from ..audit import audit
from ..db import get_conn
from ..deps import current_user, require
from ..errors import Problem
from ..schemas import ActivityIn, ActivityOut, ActivityPatch

router = APIRouter(tags=["activities"])
ACTIVITY_SQL = (
    "SELECT x.*, o.name AS owner_name, c.name AS created_by_name, a.name AS account_name, d.title AS deal_title "
    "FROM activities x LEFT JOIN users o ON o.id = x.owner_id LEFT JOIN users c ON c.id = x.created_by "
    "LEFT JOIN deals d ON d.id = x.deal_id LEFT JOIN accounts a ON a.id = COALESCE(x.account_id, d.account_id) ")


async def _activity(conn, aid) -> dict:
    cur = await conn.execute(ACTIVITY_SQL + "WHERE x.id = %s", (aid,))
    x = await cur.fetchone()
    if not x:
        raise Problem(404, "Activity not found.", code="not_found")
    return x


@router.get("/activities", response_model=list[ActivityOut], summary="Tasks and logged activity")
async def list_activities(mine: bool = False, owner_id: UUID | None = None,
                          status: str = Query("open", pattern="^(open|done|all)$"),
                          due: str | None = Query(None, pattern="^(overdue|today|week)$"),
                          kind: str | None = Query(None, pattern="^(task|call|meeting|email|note)$"),
                          account_id: UUID | None = None, deal_id: UUID | None = None, limit: int = Query(200, ge=1, le=500),
                          user=Depends(current_user), conn=Depends(get_conn)):
    where, params = ["true"], []
    if mine:
        where.append("x.owner_id = %s"); params.append(user["id"])
    elif owner_id:
        where.append("x.owner_id = %s"); params.append(owner_id)
    if status == "open":
        where.append("x.done_at IS NULL")
    elif status == "done":
        where.append("x.done_at IS NOT NULL")
    if due == "overdue":
        where.append("x.due_at < now()")
    elif due == "today":
        where.append("x.due_at < date_trunc('day', now()) + interval '1 day'")
    elif due == "week":
        where.append("x.due_at < date_trunc('day', now()) + interval '7 days'")
    if kind:
        where.append("x.kind = %s"); params.append(kind)
    if account_id:
        where.append("(x.account_id = %s OR d.account_id = %s)"); params += [account_id, account_id]
    if deal_id:
        where.append("x.deal_id = %s"); params.append(deal_id)
    order = "x.due_at NULLS LAST, x.created_at" if status == "open" else "COALESCE(x.done_at, x.created_at) DESC"
    cur = await conn.execute(ACTIVITY_SQL + f"WHERE {' AND '.join(where)} ORDER BY {order} LIMIT %s", (*params, limit))
    return await cur.fetchall()


@router.post("/activities", response_model=ActivityOut, status_code=201)
async def create_activity(body: ActivityIn, user=Depends(require("activities.edit")), conn=Depends(get_conn)):
    account_id = body.account_id
    if body.deal_id:
        cur = await conn.execute("SELECT account_id FROM deals WHERE id = %s", (body.deal_id,))
        d = await cur.fetchone()
        if not d:
            raise Problem(422, "That deal does not exist.", code="validation", fields={"deal_id": ["not found"]})
        account_id = account_id or d["account_id"]
    if account_id:
        cur = await conn.execute("SELECT 1 FROM accounts WHERE id = %s", (account_id,))
        if not await cur.fetchone():
            raise Problem(422, "That client does not exist.", code="validation", fields={"account_id": ["not found"]})
    owner = body.owner_id or user["id"]
    cur = await conn.execute("SELECT 1 FROM users WHERE id = %s AND active", (owner,))
    if not await cur.fetchone():
        raise Problem(422, "Choose an active staff member.", code="validation", fields={"owner_id": ["not staff"]})
    # notes are a record of something that happened; tasks wait to be done
    done = body.kind == "note" or (body.done and body.kind != "task")
    cur = await conn.execute(
        "INSERT INTO activities (kind, subject, body, due_at, done_at, owner_id, account_id, deal_id, created_by) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (body.kind, body.subject.strip(), body.body, body.due_at, datetime.now(timezone.utc) if done else None, owner,
         account_id, body.deal_id, user["id"]))
    aid = (await cur.fetchone())["id"]
    if account_id:
        await conn.execute("UPDATE accounts SET updated_at = now() WHERE id = %s", (account_id,))
    await audit(conn, "activity.create", actor_id=user["id"], target_type="activity", target_id=aid, kind=body.kind,
                subject=body.subject.strip(), **({"assigned_to": str(owner)} if owner != user["id"] else {}))
    return await _activity(conn, aid)


@router.patch("/activities/{aid}", response_model=ActivityOut, summary="Change a task, or mark it done or not done")
async def update_activity(aid: UUID, body: ActivityPatch, user=Depends(require("activities.edit")), conn=Depends(get_conn)):
    x = await _activity(conn, aid)
    sets, params = [], []
    for k in ("subject", "body", "owner_id"):
        v = getattr(body, k)
        if v is not None:
            sets.append(f"{k} = %s"); params.append(v.strip() if k == "subject" else v)
    if body.clear_due:
        sets.append("due_at = NULL")
    elif body.due_at is not None:
        sets.append("due_at = %s"); params.append(body.due_at)
    if body.done is not None:
        sets.append("done_at = " + ("COALESCE(done_at, now())" if body.done else "NULL"))
    if body.owner_id:
        cur = await conn.execute("SELECT 1 FROM users WHERE id = %s AND active", (body.owner_id,))
        if not await cur.fetchone():
            raise Problem(422, "Choose an active staff member.", code="validation", fields={"owner_id": ["not staff"]})
    if sets:
        await conn.execute(f"UPDATE activities SET {', '.join(sets)} WHERE id = %s", (*params, aid))
        action = "activity.done" if body.done else "activity.reopen" if body.done is False else "activity.update"
        await audit(conn, action, actor_id=user["id"], target_type="activity", target_id=aid, subject=x["subject"])
    return await _activity(conn, aid)


@router.delete("/activities/{aid}", status_code=204, summary="Delete an activity (its author or a super admin)")
async def delete_activity(aid: UUID, user=Depends(require("activities.edit")), conn=Depends(get_conn)):
    x = await _activity(conn, aid)
    if x["created_by"] != user["id"] and user["role"] != "super_admin":
        raise Problem(403, "Only whoever added it, or a super admin, can delete it.", code="forbidden")
    await conn.execute("DELETE FROM activities WHERE id = %s", (aid,))
    await audit(conn, "activity.delete", actor_id=user["id"], target_type="activity", target_id=aid, subject=x["subject"])
    return Response(status_code=204)
