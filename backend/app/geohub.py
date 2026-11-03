"""Calls to Geohub's CRM link (/crm-link/* there), signed with GEOHUB_LINK_KEY. Geohub keeps the licences; the CRM
reads customers and website requests from it, sets customers up, and switches on the licence a paid invoice buys."""
import logging

import httpx

from .config import settings
from .errors import Problem

log = logging.getLogger("geohub")
# Tests replace this with a mock transport.
transport: httpx.AsyncBaseTransport | None = None


class GeohubError(Exception):
    """Geohub could not do it. The message says why, in words staff can act on."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def configured() -> bool:
    return bool(settings.geohub_url and settings.geohub_link_key)


def _base() -> str:
    return settings.geohub_url + settings.geohub_api_prefix + "/crm-link"


async def call(method: str, path: str, *, json: dict | None = None, params: dict | None = None):
    if not configured():
        raise GeohubError("The CRM is not linked to Geohub yet: set GEOHUB_URL and GEOHUB_LINK_KEY in the CRM's variables.")
    try:
        async with httpx.AsyncClient(timeout=20, transport=transport) as c:
            r = await c.request(method, _base() + path, json=json, params=params,
                                headers={"Authorization": f"Bearer {settings.geohub_link_key}", "Accept": "application/json"})
    except httpx.HTTPError as e:
        log.warning("geohub %s %s failed: %s", method, path, e)
        raise GeohubError(f"Geohub did not answer at {settings.geohub_url}. Check GEOHUB_URL and that Geohub is running.")
    if r.status_code < 400:
        return r.json()
    try:
        detail = r.json().get("detail") or ""
    except ValueError:
        detail = ""
    if r.status_code == 401:
        raise GeohubError("Geohub refused the link key: GEOHUB_LINK_KEY here must equal CRM_LINK_KEY in Geohub.", 401)
    if r.status_code == 404 and path in ("/orgs", "/requests"):
        raise GeohubError("Geohub's CRM link is off: set CRM_LINK_KEY in Geohub's variables (the same value as "
                          "GEOHUB_LINK_KEY here), and check GEOHUB_URL.", 404)
    if r.status_code == 404 and not detail:
        detail = "Geohub's CRM link is off or not found: check GEOHUB_URL, and CRM_LINK_KEY in Geohub."
    raise GeohubError(detail or f"Geohub answered {r.status_code}.", r.status_code)


async def must(method: str, path: str, **kw):
    """call(), turning a failure into an error for the person who asked."""
    try:
        return await call(method, path, **kw)
    except GeohubError as e:
        status = e.status if e.status in (404, 409, 422) else 502
        raise Problem(status, str(e), code="geohub")
