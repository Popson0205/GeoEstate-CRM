"""One-time links to set a password (new staff, 72 hours) or reset it (2 hours). Only a hash is stored; a new link
cancels the person's older ones."""
from .errors import Problem
from .security import new_token, hash_token

HOURS = {"set": 72, "reset": 2}


async def issue(conn, user_id, purpose: str) -> str:
    raw, digest = new_token()
    await conn.execute("UPDATE password_tokens SET used_at = now() WHERE user_id = %s AND used_at IS NULL", (user_id,))
    await conn.execute("INSERT INTO password_tokens (user_id, token_hash, purpose, expires_at) "
                       "VALUES (%s, %s, %s, now() + make_interval(hours => %s))", (user_id, digest, purpose, HOURS[purpose]))
    return raw


async def lookup(conn, raw: str, lock: bool = False) -> dict:
    cur = await conn.execute(
        "SELECT t.id, t.user_id, t.purpose, t.used_at, t.expires_at < now() AS expired, u.email, u.name, u.active "
        "FROM password_tokens t JOIN users u ON u.id = t.user_id WHERE t.token_hash = %s" + (" FOR UPDATE OF t" if lock else ""),
        (hash_token(raw),))
    t = await cur.fetchone()
    if not t or not t["active"]:
        raise Problem(404, "This link is not valid. Ask for a new one.", code="invalid_link")
    if t["used_at"]:
        raise Problem(410, "This link was already used, or a newer one was sent. Ask for a new one.", code="link_used")
    if t["expired"]:
        raise Problem(410, "This link has expired. Ask for a new one.", code="link_expired")
    return t
