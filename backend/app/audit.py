from psycopg.types.json import Jsonb


async def audit(conn, action: str, *, actor_id=None, target_type: str | None = None, target_id=None, **details) -> None:
    """Record a staff action in the activity log."""
    await conn.execute("INSERT INTO audit_log (actor_id, action, target_type, target_id, details) VALUES (%s, %s, %s, %s, %s)",
                       (actor_id, action, target_type, str(target_id) if target_id else None, Jsonb(details)))
