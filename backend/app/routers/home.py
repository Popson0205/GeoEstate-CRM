"""The home page's numbers, and the log of what staff did."""
from fastapi import APIRouter, Depends, Query

from ..db import get_conn
from ..deps import current_user, require
from ..schemas import AuditOut, HomeOut
from .activities import ACTIVITY_SQL

router = APIRouter(tags=["home"])
STAGES = ("new", "contacted", "demo", "proposal", "won", "lost")


@router.get("/home", response_model=HomeOut)
async def home(user=Depends(current_user), conn=Depends(get_conn)):
    cur = await conn.execute(
        "SELECT stage, count(*) AS count, COALESCE(sum(amount_ngn), 0) AS value_ngn FROM deals "
        "WHERE stage NOT IN ('won','lost') OR closed_at > date_trunc('month', now()) GROUP BY stage")
    by = {r["stage"]: r for r in await cur.fetchall()}
    pipeline = [{"stage": s, "count": by[s]["count"] if s in by else 0, "value_ngn": by[s]["value_ngn"] if s in by else 0} for s in STAGES]
    cur = await conn.execute("SELECT status, count(*) AS n FROM accounts GROUP BY status")
    accounts = {"lead": 0, "customer": 0, "former": 0} | {r["status"]: r["n"] for r in await cur.fetchall()}
    cur = await conn.execute(
        "SELECT count(*) FILTER (WHERE done_at IS NULL) AS open, count(*) FILTER (WHERE done_at IS NULL AND due_at < now()) AS overdue "
        "FROM activities WHERE owner_id = %s AND kind = 'task'", (user["id"],))
    mine = await cur.fetchone()
    cur = await conn.execute(ACTIVITY_SQL + "WHERE x.owner_id = %s AND x.done_at IS NULL AND x.kind IN ('task','call','meeting','email') "
                             "ORDER BY x.due_at NULLS LAST, x.created_at LIMIT 8", (user["id"],))
    my_tasks = await cur.fetchall()
    cur = await conn.execute(ACTIVITY_SQL + "WHERE x.done_at IS NOT NULL ORDER BY x.done_at DESC LIMIT 10")
    recent = await cur.fetchall()
    cur = await conn.execute(
        "SELECT COALESCE(sum(owed), 0) AS unpaid, COALESCE(sum(owed) FILTER (WHERE due_date < current_date), 0) AS overdue, "
        "  count(*) FILTER (WHERE due_date < current_date) AS overdue_n "
        "FROM (SELECT i.due_date, i.total_ngn - COALESCE((SELECT sum(amount_ngn) FROM payments p WHERE p.invoice_id = i.id), 0) AS owed "
        "      FROM invoices i WHERE i.status = 'issued') x")
    money = await cur.fetchone()
    cur = await conn.execute("SELECT COALESCE(sum(amount_ngn), 0) AS n FROM payments WHERE paid_on >= date_trunc('month', current_date)")
    received = (await cur.fetchone())["n"]
    return {"unpaid_ngn": money["unpaid"], "overdue_ngn": money["overdue"], "overdue_invoices": money["overdue_n"],
            "received_this_month_ngn": received, "pipeline": pipeline, "won_this_month_ngn": by["won"]["value_ngn"] if "won" in by else 0, "accounts": accounts,
            "my_open_tasks": mine["open"], "my_overdue": mine["overdue"], "my_tasks": my_tasks, "recent": recent}


@router.get("/audit", response_model=list[AuditOut], summary="What staff did, newest first (super admins and finance)")
async def audit_log(before: int | None = None, actor_id: str | None = None, limit: int = Query(100, ge=1, le=200),
                    user=Depends(require("audit.view")), conn=Depends(get_conn)):
    where, params = ["true"], []
    if before:
        where.append("l.id < %s"); params.append(before)
    if actor_id:
        where.append("l.actor_id = %s"); params.append(actor_id)
    cur = await conn.execute("SELECT l.*, u.name AS actor_name FROM audit_log l LEFT JOIN users u ON u.id = l.actor_id "
                             f"WHERE {' AND '.join(where)} ORDER BY l.id DESC LIMIT %s", (*params, limit))
    return await cur.fetchall()
