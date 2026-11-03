"""The first super admin (SUPER_ADMIN_EMAIL, geoestate.ng@gmail.com by default): created on start-up when missing,
and emailed a link to choose a password. Without email set up, the link is written to the server log."""
import logging

from . import links
from .config import settings
from .mailer import send_email

log = logging.getLogger("bootstrap")


async def ensure_super_admin(conn) -> None:
    email = settings.super_admin_email.strip().lower()
    if not email:
        return
    cur = await conn.execute("SELECT 1 FROM users WHERE lower(email) = %s", (email,))
    if await cur.fetchone():
        return
    cur = await conn.execute("INSERT INTO users (email, name, role) VALUES (%s, %s, 'super_admin') RETURNING id",
                             (email, settings.super_admin_name))
    uid = (await cur.fetchone())["id"]
    raw = await links.issue(conn, uid, "set")
    await conn.commit()
    url = f"{settings.app_url}/set-password?token={raw}"
    log.warning("super admin %s created; set the password at %s (the link works once, within 72 hours)", email, url)
    await send_email(email, "Your GeoEstate CRM is ready",
                     "The GeoEstate CRM is set up, and this address is its super admin.\n\nChoose your password with the "
                     "button below (the link works once, within 72 hours). Then set up two-step sign-in with an "
                     "authenticator app on your phone, and add your staff.", action=("Choose your password", url))
