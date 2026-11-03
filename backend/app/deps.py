from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import ratelimit, roles
from .db import get_conn
from .errors import Problem
from .security import decode_access

bearer = HTTPBearer(auto_error=False)
USER_SQL = ("SELECT id, email, name, role, active, (totp_enabled_at IS NOT NULL) AS mfa_enabled, last_sign_in_at, created_at "
            "FROM users ")


async def current_user(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                       conn=Depends(get_conn)) -> dict:
    """A signed-in staff member. Tokens are only issued after two-step sign-in, so every caller has passed it."""
    if not creds:
        raise Problem(401, "Sign in to continue.", code="unauthenticated", headers={"WWW-Authenticate": "Bearer"})
    uid = decode_access(creds.credentials)
    cur = await conn.execute(USER_SQL + "WHERE id = %s", (uid,))
    user = await cur.fetchone()
    if not user or not user["active"]:
        raise Problem(401, "This account cannot sign in.", code="invalid_token")
    ratelimit.hit(f"user:{user['id']}", 600, 60)
    return user


def require(perm: str):
    async def dep(user=Depends(current_user)) -> dict:
        if not roles.can(user["role"], perm):
            raise Problem(403, f"Your role ({roles.ROLE_NAMES[user['role']]}) cannot do this.", code="forbidden")
        return user
    return dep
