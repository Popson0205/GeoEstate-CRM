"""Passwords (bcrypt), sign-in tokens (short-lived JWTs plus rotating refresh tokens), and one-time links."""
import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import anyio
import bcrypt
import jwt

from .config import settings
from .errors import Problem


def _prehash(pw: str) -> bytes:
    # bcrypt ignores everything after 72 bytes; hashing first keeps long passphrases intact.
    return base64.b64encode(hashlib.sha256(pw.encode()).digest())


async def hash_password(pw: str) -> str:
    return await anyio.to_thread.run_sync(lambda: bcrypt.hashpw(_prehash(pw), bcrypt.gensalt()).decode())


async def verify_password(pw: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    return await anyio.to_thread.run_sync(lambda: bcrypt.checkpw(_prehash(pw), hashed.encode()))


_DUMMY = bcrypt.hashpw(b"x", bcrypt.gensalt()).decode()


async def burn_password_check(pw: str) -> None:
    """Spend the same time as a real check, so unknown emails cannot be told apart by timing."""
    await verify_password(pw, _DUMMY)


def make_access_token(user_id: UUID) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "typ": "access", "iat": now,
                       "exp": now + timedelta(minutes=settings.access_token_minutes)}, settings.jwt_secret, algorithm="HS256")


def decode_access(token: str) -> str:
    try:
        p = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise Problem(401, "Your session has expired.", code="token_expired")
    except jwt.PyJWTError:
        raise Problem(401, "Invalid token.", code="invalid_token")
    if p.get("typ") != "access":
        raise Problem(401, "Invalid token.", code="invalid_token")
    return p["sub"]


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(40)
    return raw, hash_token(raw)
