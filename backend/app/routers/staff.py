"""GeoEstate staff: super admins add people with a role (they are emailed a link to choose a password, then set up
two-step sign-in), change roles, reset a lost phone's two-step sign-in, and turn accounts off. Everyone can see who
is on the staff, to assign work."""
from uuid import UUID

from fastapi import APIRouter, Depends

from .. import links, roles
from ..audit import audit
from ..config import settings
from ..db import get_conn
from ..deps import current_user, require
from ..errors import Problem
from ..mailer import send_email
from ..schemas import StaffBrief, StaffIn, StaffOut, StaffPatch

router = APIRouter(prefix="/staff", tags=["staff"])
STAFF_SQL = ("SELECT id, email, name, role, active, (totp_enabled_at IS NOT NULL) AS mfa_enabled, "
             "(password_hash IS NOT NULL) AS password_set, last_sign_in_at, created_at FROM users ")


async def _one(conn, uid) -> dict:
    cur = await conn.execute(STAFF_SQL + "WHERE id = %s", (uid,))
    s = await cur.fetchone()
    if not s:
        raise Problem(404, "Staff member not found.", code="not_found")
    return s


async def _super_admins_left(conn, without) -> int:
    cur = await conn.execute("SELECT count(*) AS n FROM users WHERE role = 'super_admin' AND active AND id <> %s", (without,))
    return (await cur.fetchone())["n"]


@router.get("", response_model=list[StaffOut], summary="Everyone on the staff")
async def list_staff(user=Depends(current_user), conn=Depends(get_conn)):
    cur = await conn.execute(STAFF_SQL + "ORDER BY active DESC, array_position(ARRAY['super_admin','account_manager','support','finance'], role), lower(name)")
    return await cur.fetchall()


@router.get("/brief", response_model=list[StaffBrief], summary="Active staff, to assign work to")
async def brief(user=Depends(current_user), conn=Depends(get_conn)):
    cur = await conn.execute("SELECT id, name FROM users WHERE active ORDER BY lower(name)")
    return await cur.fetchall()


async def _welcome(conn, s: dict, by: dict) -> bool:
    raw = await links.issue(conn, s["id"], "set")
    return await send_email(s["email"], "Your GeoEstate CRM account",
                            f"Hello {s['name'].split()[0]},\n\n{by['name']} added you to the GeoEstate CRM as "
                            f"{roles.ROLE_NAMES[s['role']]}.\n\nChoose your password with the button below (the link works once, "
                            "within 72 hours). Then set up two-step sign-in with an authenticator app on your phone, such as "
                            "Google Authenticator or Microsoft Authenticator: the CRM asks for its code every time you sign in.",
                            action=("Choose your password", f"{settings.app_url}/set-password?token={raw}"))


@router.post("", response_model=StaffOut, status_code=201, summary="Add a staff member (super admins)")
async def add_staff(body: StaffIn, user=Depends(require("staff.manage")), conn=Depends(get_conn)):
    cur = await conn.execute("SELECT 1 FROM users WHERE lower(email) = lower(%s)", (body.email,))
    if await cur.fetchone():
        raise Problem(409, "Someone with that email is already on the staff.", code="email_taken", fields={"email": ["taken"]})
    cur = await conn.execute("INSERT INTO users (email, name, role, invited_by) VALUES (%s, %s, %s, %s) RETURNING id",
                             (body.email.lower(), body.name.strip(), body.role, user["id"]))
    s = await _one(conn, (await cur.fetchone())["id"])
    await _welcome(conn, s, user)
    await audit(conn, "staff.add", actor_id=user["id"], target_type="user", target_id=s["id"], email=s["email"], role=s["role"])
    return s


@router.patch("/{uid}", response_model=StaffOut, summary="Change a staff member's name, role, or turn them off (super admins)")
async def update_staff(uid: UUID, body: StaffPatch, user=Depends(require("staff.manage")), conn=Depends(get_conn)):
    s = await _one(conn, uid)
    if uid == user["id"] and (body.role not in (None, s["role"]) or body.active is False):
        raise Problem(409, "Ask another super admin to change your own role or turn you off.", code="own_account")
    losing_super = s["role"] == "super_admin" and ((body.role and body.role != "super_admin") or body.active is False)
    if losing_super and not await _super_admins_left(conn, uid):
        raise Problem(409, "The CRM needs at least one active super admin.", code="last_super_admin")
    await conn.execute("UPDATE users SET name = COALESCE(%s, name), role = COALESCE(%s, role), active = COALESCE(%s, active) WHERE id = %s",
                       (body.name.strip() if body.name else None, body.role, body.active, uid))
    if body.active is False:                            # signed out everywhere at once
        await conn.execute("UPDATE refresh_tokens SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL", (uid,))
    await audit(conn, "staff.update", actor_id=user["id"], target_type="user", target_id=uid, **body.model_dump(exclude_none=True))
    return await _one(conn, uid)


@router.post("/{uid}/send-link", status_code=202, summary="Email a new set-password link (super admins)")
async def send_link(uid: UUID, user=Depends(require("staff.manage")), conn=Depends(get_conn)):
    s = await _one(conn, uid)
    if not s["active"]:
        raise Problem(409, "Turn this account back on first.", code="inactive")
    sent = await _welcome(conn, s, user)
    await audit(conn, "staff.send_link", actor_id=user["id"], target_type="user", target_id=uid)
    return {"sent": sent}


@router.post("/{uid}/reset-mfa", response_model=StaffOut, summary="Reset two-step sign-in, for a lost phone (super admins)")
async def reset_mfa(uid: UUID, user=Depends(require("staff.manage")), conn=Depends(get_conn)):
    """They set it up again at their next sign-in. Their sessions end now."""
    if uid == user["id"]:
        raise Problem(409, "Ask another super admin to reset yours.", code="own_account")
    s = await _one(conn, uid)
    await conn.execute("UPDATE users SET totp_secret = NULL, totp_enabled_at = NULL, totp_last_step = NULL WHERE id = %s", (uid,))
    await conn.execute("DELETE FROM recovery_codes WHERE user_id = %s", (uid,))
    await conn.execute("UPDATE refresh_tokens SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL", (uid,))
    await send_email(s["email"], "Your GeoEstate CRM two-step sign-in was reset",
                     f"Hello {s['name'].split()[0]},\n\n{user['name']} reset two-step sign-in on your GeoEstate CRM account. At your "
                     "next sign-in, set it up again with your authenticator app.\n\nIf you did not ask for this, tell them at once.")
    await audit(conn, "staff.reset_mfa", actor_id=user["id"], target_type="user", target_id=uid)
    return await _one(conn, uid)
