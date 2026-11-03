"""Email to staff (welcome links, password resets) through Brevo over HTTPS, as Geohub does. Without BREVO_API_KEY
the email is written to the log instead, link included, so a first deploy can still be set up. Sending never
raises: a failed email is logged and the action that caused it still succeeds."""
import asyncio
import base64
import html
import logging
import re

import httpx

from .config import settings

log = logging.getLogger("mailer")
BREVO_URL = "https://api.brevo.com/v3/smtp/email"
NAVY, GREEN = "#1b2b5e", "#3c9a3c"
# Tests replace this with a mock transport.
transport: httpx.AsyncBaseTransport | None = None


def _address(value: str) -> tuple[str, str]:
    m = re.match(r"^\s*(.*?)\s*<\s*([^<>\s]+@[^<>\s]+)\s*>\s*$", value)
    return (m.group(1).strip().strip('"'), m.group(2)) if m else ("", value.strip())


def render_html(subject: str, body: str, action: tuple[str, str] | None) -> str:
    def para(p: str) -> str:
        return f'<p style="margin:0 0 14px">{html.escape(p).replace(chr(10), "<br>")}</p>'
    paras = "".join(para(p) for p in body.strip().split("\n\n") if p.strip())
    button = ""
    if action:
        button = (f'<p style="margin:22px 0"><a href="{html.escape(action[1], quote=True)}" style="display:inline-block;'
                  f'background:{NAVY};color:#ffffff;text-decoration:none;font-weight:600;padding:12px 20px;border-radius:8px">'
                  f'{html.escape(action[0])}</a></p>')
    logo = html.escape(f"{settings.app_url}/logo.png", quote=True)
    return ('<!doctype html><html><body style="margin:0;padding:24px;background:#f3f5f8;'
            'font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1a2233">'
            '<div style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #dfe4ec;border-radius:12px;padding:28px">'
            f'<div style="margin-bottom:18px"><img src="{logo}" alt="GeoEstate" style="height:56px"></div>'
            f'<h1 style="font-size:20px;line-height:1.3;margin:0 0 16px;color:{NAVY}">{html.escape(subject)}</h1>'
            f'<div style="font-size:15px;line-height:1.55">{paras}{button}</div></div>'
            '<p style="max-width:520px;margin:14px auto 0;font-size:12px;color:#6a7486;text-align:center">'
            'GeoEstate NIG Limited · staff CRM</p></body></html>')


def _text(body: str, action) -> str:
    return body.strip() + (f"\n\n{action[0]}: {action[1]}" if action else "") + "\n"


async def send_email(to: str, subject: str, body: str, *, action: tuple[str, str] | None = None,
                     attachments: list[tuple[str, bytes]] | None = None) -> bool:
    """attachments: (file name, content) pairs, such as an invoice PDF."""
    if not settings.brevo_api_key:
        log.warning("email not sent (no BREVO_API_KEY): to=%s subject=%s attachments=%s\n%s", to, subject,
                    [n for n, _ in attachments or []], _text(body, action))
        return False
    name, email = _address(settings.mail_from)
    payload = {"sender": {"email": email, **({"name": name} if name else {})}, "to": [{"email": to}], "subject": subject,
               "htmlContent": render_html(subject, body, action), "textContent": _text(body, action)}
    if attachments:
        payload["attachment"] = [{"name": n, "content": base64.b64encode(c).decode()} for n, c in attachments]
    if settings.mail_reply_to:
        payload["replyTo"] = {"email": _address(settings.mail_reply_to)[1]}
    try:
        async with httpx.AsyncClient(timeout=15, transport=transport) as c:
            for attempt in range(3):
                r = await c.post(BREVO_URL, json=payload, headers={"api-key": settings.brevo_api_key, "accept": "application/json"})
                if r.status_code < 400:
                    return True
                if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"Brevo refused the email ({r.status_code}): {r.text[:300]}")
    except Exception:  # noqa: BLE001
        log.exception("failed to send email to %s", to)
    return False
