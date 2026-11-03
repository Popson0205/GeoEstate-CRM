"""Simple fixed-window rate limits kept in memory: the CRM runs as one small service with a few dozen staff, so
there is no need for Redis. Limits sign-in guessing per address and per account."""
import time

from fastapi import Request

from .config import settings
from .errors import Problem

_hits: dict[str, tuple[int, float]] = {}


def hit(key: str, limit: int, window: int) -> None:
    if not settings.rate_limit_enabled:
        return
    now = time.monotonic()
    n, start = _hits.get(key, (0, now))
    if now - start > window:
        n, start = 0, now
    n += 1
    _hits[key] = (n, start)
    if len(_hits) > 50_000:                       # forget old windows now and then
        for k in [k for k, (_, s) in _hits.items() if now - s > 3600]:
            _hits.pop(k, None)
    if n > limit:
        raise Problem(429, "Too many tries. Wait a few minutes, then try again.", code="rate_limited",
                      headers={"Retry-After": str(int(window - (now - start)) + 1)})


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def limit(name: str, per: int, window: int = 60):
    def dep(request: Request):
        hit(f"{name}:{client_ip(request)}", per, window)
    return dep


def reset() -> None:
    _hits.clear()
