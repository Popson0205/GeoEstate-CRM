"""Signing in. Two-step sign-in is required for every staff member:

    POST /auth/login {email, password}       -> {next: "mfa", token}  or, the first time, {next: "enroll", token}
    POST /auth/mfa {token, code}             -> a session
    POST /auth/enroll/start {token}          -> the authenticator app's secret (as a QR code's contents and as text)
    POST /auth/enroll/finish {token, code}   -> a session, and ten recovery codes shown once

No session is ever issued without a code from the app (or a recovery code)."""
from fastapi import APIRouter, Depends, Request, Response

from .. import links, mfa, ratelimit, roles
from ..audit import audit
from ..config import settings
from ..db import get_conn
from ..deps import current_user
from ..errors import Problem
from ..mailer import send_email
from ..schemas import (ChangePasswordIn, CodeIn, EnrolledOut, EnrollStartOut, ForgotIn, LinkOut, LoginIn, MyCodeIn,
                       RecoveryCodesOut, RefreshIn, SessionOut, SetPasswordIn, StepOut, TokenIn, UserOut)
from ..security import (burn_password_check, hash_password, hash_token, make_access_token, new_token,
                        verify_password)

router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(tags=["auth"])


def user_out(u: dict) -> dict:
    return {"id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"], "role_name": roles.ROLE_NAMES[u["role"]],
            "perms": roles.perms_of(u["role"]), "mfa_enabled": u["mfa_enabled"]}


async def _user(conn, uid) -> dict:
    cur = await conn.execute("SELECT id, email, name, role, active, (totp_enabled_at IS NOT NULL) AS mfa_enabled "
                             "FROM users WHERE id = %s", (uid,))
    u = await cur.fetchone()
    if not u or not u["active"]:
        raise Problem(401, "This account cannot sign in.", code="invalid_token")
    return u


async def _session(conn, u: dict) -> dict:
    raw, digest = new_token()
    await conn.execute("INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, now() + make_interval(days => %s))",
                       (u["id"], digest, settings.refresh_token_days))
    await conn.execute("UPDATE users SET last_sign_in_at = now() WHERE id = %s", (u["id"],))
    return {"access_token": make_access_token(u["id"]), "refresh_token": raw, "expires_in": settings.access_token_minutes * 60,
            "user": user_out(u)}


async def _next_step(conn, uid) -> dict:
    u = await _user(conn, uid)
    return {"next": "mfa", "token": mfa.challenge_token(uid)} if u["mfa_enabled"] else \
        {"next": "enroll", "token": mfa.challenge_token(uid, "enroll")}


@router.post("/login", response_model=StepOut, dependencies=[Depends(ratelimit.limit("login", 20, 60))])
async def login(body: LoginIn, conn=Depends(get_conn)):
    ratelimit.hit(f"login-email:{body.email.lower()}", 10, 900)
    cur = await conn.execute("SELECT id, password_hash, active FROM users WHERE lower(email) = lower(%s)", (body.email,))
    u = await cur.fetchone()
    if not u or not u["password_hash"]:
        await burn_password_check(body.password)
    if not u or not u["active"] or not await verify_password(body.password, u["password_hash"]):
        raise Problem(401, "Wrong email or password.", code="bad_credentials")
    return await _next_step(conn, u["id"])


@router.post("/mfa", response_model=SessionOut, summary="Finish signing in with a code from the authenticator app")
async def verify(body: CodeIn, conn=Depends(get_conn)):
    uid = mfa.read_challenge(body.token)
    ratelimit.hit(f"mfa:{uid}", 10, 900)
    u = await _user(conn, uid)
    try:
        how = await mfa.check(conn, uid, body.code)
    except Problem:
        await audit(conn, "auth.mfa_failed", actor_id=uid)
        await conn.commit()
        raise
    if how == "recovery":
        await audit(conn, "auth.recovery_code_used", actor_id=uid)
    return await _session(conn, u)


@router.post("/enroll/start", response_model=EnrollStartOut, summary="Set up two-step sign-in: a new secret for the app")
async def enroll_start(body: TokenIn, conn=Depends(get_conn)):
    uid = mfa.read_challenge(body.token, "enroll")
    u = await _user(conn, uid)
    if u["mfa_enabled"]:
        raise Problem(409, "Two-step sign-in is already set up. Sign in again.", code="mfa_already_on")
    secret = mfa.new_secret()
    await conn.execute("UPDATE users SET totp_secret = %s, totp_last_step = NULL WHERE id = %s", (mfa.seal(secret), uid))
    return {"secret": secret, "otpauth_url": mfa.otpauth_url(secret, u["email"])}


@router.post("/enroll/finish", response_model=EnrolledOut, summary="Confirm the app's code, and sign in")
async def enroll_finish(body: CodeIn, conn=Depends(get_conn)):
    uid = mfa.read_challenge(body.token, "enroll")
    ratelimit.hit(f"enroll:{uid}", 15, 900)
    u = await _user(conn, uid)
    cur = await conn.execute("SELECT totp_secret FROM users WHERE id = %s", (uid,))
    stored = (await cur.fetchone())["totp_secret"]
    if u["mfa_enabled"] or not stored:
        raise Problem(409, "Start the setup again.", code="mfa_not_started")
    step = mfa.matching_step(mfa.unseal(stored), body.code)
    if step is None:
        raise Problem(422, "That code is not right. Check the phone's time is set automatically, and enter the code the "
                           "app shows now.", code="bad_code", fields={"code": ["not right"]})
    await conn.execute("UPDATE users SET totp_enabled_at = now(), totp_last_step = %s WHERE id = %s", (step, uid))
    codes = mfa.new_recovery_codes()
    await mfa.store_recovery_codes(conn, uid, codes)
    await audit(conn, "auth.mfa_enrolled", actor_id=uid)
    return {**await _session(conn, {**u, "mfa_enabled": True}), "recovery_codes": codes}


@router.post("/refresh", response_model=SessionOut)
async def refresh(body: RefreshIn, conn=Depends(get_conn)):
    cur = await conn.execute("SELECT id, user_id, revoked_at, expires_at < now() AS expired FROM refresh_tokens "
                             "WHERE token_hash = %s FOR UPDATE", (hash_token(body.refresh_token),))
    rt = await cur.fetchone()
    if not rt or rt["revoked_at"] or rt["expired"]:
        raise Problem(401, "Your session has ended. Sign in again.", code="invalid_token")
    await conn.execute("UPDATE refresh_tokens SET revoked_at = now() WHERE id = %s", (rt["id"],))
    return await _session(conn, await _user(conn, rt["user_id"]))


@router.post("/logout", status_code=204)
async def logout(body: RefreshIn, conn=Depends(get_conn)):
    await conn.execute("UPDATE refresh_tokens SET revoked_at = now() WHERE token_hash = %s AND revoked_at IS NULL",
                       (hash_token(body.refresh_token),))
    return Response(status_code=204)


@router.get("/password-link/{token}", response_model=LinkOut)
async def password_link(token: str, conn=Depends(get_conn)):
    t = await links.lookup(conn, token)
    return {"email": t["email"], "name": t["name"], "purpose": t["purpose"]}


@router.post("/set-password", response_model=StepOut, summary="Choose a password from an emailed link; then two-step sign-in",
             dependencies=[Depends(ratelimit.limit("set-password", 20, 3600))])
async def set_password(body: SetPasswordIn, conn=Depends(get_conn)):
    t = await links.lookup(conn, body.token, lock=True)
    await conn.execute("UPDATE users SET password_hash = %s WHERE id = %s", (await hash_password(body.password), t["user_id"]))
    await conn.execute("UPDATE password_tokens SET used_at = now() WHERE id = %s", (t["id"],))
    await conn.execute("UPDATE refresh_tokens SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL", (t["user_id"],))
    await audit(conn, "auth.password_set", actor_id=t["user_id"], via=t["purpose"])
    return await _next_step(conn, t["user_id"])


@router.post("/forgot-password", status_code=202, dependencies=[Depends(ratelimit.limit("forgot", 5, 3600))])
async def forgot_password(body: ForgotIn, conn=Depends(get_conn)):
    """Always answers the same, so it never reveals which emails belong to staff."""
    cur = await conn.execute("SELECT id, name, email FROM users WHERE lower(email) = lower(%s) AND active", (body.email,))
    u = await cur.fetchone()
    if u:
        raw = await links.issue(conn, u["id"], "reset")
        await send_email(u["email"], "Choose a new GeoEstate CRM password",
                         f"Hello {u['name'].split()[0]},\n\nSomeone asked to reset your GeoEstate CRM password. If it was you, "
                         "choose a new one below; the link works once, within 2 hours. If it was not you, ignore this email.",
                         action=("Choose a new password", f"{settings.app_url}/set-password?token={raw}"))
    return {"sent": True}


@router.post("/change-password", status_code=204)
async def change_password(body: ChangePasswordIn, user=Depends(current_user), conn=Depends(get_conn)):
    cur = await conn.execute("SELECT password_hash FROM users WHERE id = %s", (user["id"],))
    if not await verify_password(body.current_password, (await cur.fetchone())["password_hash"]):
        raise Problem(422, "The current password is not right.", code="bad_credentials", fields={"current_password": ["not right"]})
    await conn.execute("UPDATE users SET password_hash = %s WHERE id = %s", (await hash_password(body.new_password), user["id"]))
    await audit(conn, "auth.password_change", actor_id=user["id"])
    return Response(status_code=204)


@router.post("/recovery-codes", response_model=RecoveryCodesOut, summary="New recovery codes (the old ones stop working)")
async def new_recovery_codes(body: MyCodeIn, user=Depends(current_user), conn=Depends(get_conn)):
    ratelimit.hit(f"codes:{user['id']}", 10, 900)
    await mfa.check(conn, user["id"], body.code)
    codes = mfa.new_recovery_codes()
    await mfa.store_recovery_codes(conn, user["id"], codes)
    await audit(conn, "auth.recovery_codes", actor_id=user["id"])
    return {"recovery_codes": codes}


@me_router.get("/me", response_model=UserOut)
async def me(user=Depends(current_user)):
    return user_out(user)
