from app.config import settings
from conftest import OUTBOX, Staff, code, token_from, uid


def test_the_super_admin_is_created_and_must_set_up_two_step_sign_in(client, boss):
    first = next(m for m in OUTBOX if m["to"] == settings.super_admin_email)
    assert "super admin" in first["body"] and "set-password?token=" in first["action"][1]
    assert len(boss.recovery) == 10
    me = boss.get("/me").json()
    assert me["role"] == "super_admin" and me["mfa_enabled"] and "staff.manage" in me["perms"]
    # the password alone never gives a session
    step = client.post("/auth/login", json={"email": boss.email, "password": boss.password}).json()
    assert step["next"] == "mfa" and "access_token" not in step
    assert client.get("/me", headers={"Authorization": f"Bearer {step['token']}"}).status_code == 401
    assert client.post("/auth/mfa", json={"token": step["token"], "code": "000000"}).status_code == 401
    ok = client.post("/auth/mfa", json={"token": step["token"], "code": code(boss.secret)})
    assert ok.status_code == 200 and ok.json()["user"]["email"] == boss.email
    # a recovery code works once
    step = client.post("/auth/login", json={"email": boss.email, "password": boss.password}).json()
    assert client.post("/auth/mfa", json={"token": step["token"], "code": boss.recovery[0]}).status_code == 200
    assert client.post("/auth/mfa", json={"token": step["token"], "code": boss.recovery[0]}).status_code == 401
    assert client.post("/auth/login", json={"email": boss.email, "password": "wrong-password"}).status_code == 401


def test_refresh_and_sign_out(client, boss):
    s = boss.session
    r = client.post("/auth/refresh", json={"refresh_token": s["refresh_token"]})
    assert r.status_code == 200
    assert client.post("/auth/refresh", json={"refresh_token": s["refresh_token"]}).status_code == 401   # used once
    new = r.json()["refresh_token"]
    assert client.post("/auth/logout", json={"refresh_token": new}).status_code == 204
    assert client.post("/auth/refresh", json={"refresh_token": new}).status_code == 401


def test_staff_are_added_and_managed_by_super_admins(client, boss, hire):
    manager = hire("account_manager", "Funke Ola")
    assert manager.get("/me").json()["role_name"] == "Account manager"
    support = hire("support", "Bayo Ade")
    assert support.post("/staff", json={"email": f"{uid()}@x.example", "name": "No", "role": "support"}).status_code == 403
    assert boss.post("/staff", json={"email": manager.email.upper(), "name": "Again", "role": "support"}).status_code == 409
    listed = {s["email"]: s for s in support.get("/staff").json()}
    assert listed[manager.email]["mfa_enabled"] and listed[manager.email]["password_set"]
    assert [x["name"] for x in support.get("/staff/brief").json()].count("Funke Ola") == 1

    # a new hire who has not chosen a password yet can be sent a fresh link
    email = f"{uid()}@geoestate.example"
    pending = boss.post("/staff", json={"email": email, "name": "Late Starter", "role": "finance"}).json()
    assert not pending["password_set"]
    old = token_from(OUTBOX[-1])
    assert boss.post(f"/staff/{pending['id']}/send-link").status_code == 202
    assert client.get(f"/auth/password-link/{old}").status_code == 410      # the older link stops working
    Staff(client, email)

    # a lost phone: reset, and they set it up again at the next sign-in
    assert boss.post(f"/staff/{support.id}/reset-mfa").json()["mfa_enabled"] is False
    assert "reset" in OUTBOX[-1]["subject"]
    assert support.get("/me").status_code == 200           # the access token runs out by itself; refresh no longer works
    assert client.post("/auth/refresh", json={"refresh_token": support.session["refresh_token"]}).status_code == 401
    step = client.post("/auth/login", json={"email": support.email, "password": support.password}).json()
    assert step["next"] == "enroll"

    # turned off: no sign-in, history kept
    off = boss.patch(f"/staff/{manager.id}", json={"active": False}).json()
    assert off["active"] is False
    assert manager.get("/me").status_code == 401
    assert client.post("/auth/login", json={"email": manager.email, "password": manager.password}).status_code == 401
    # nobody locks the CRM without a super admin
    assert boss.patch(f"/staff/{boss.id}", json={"role": "support"}).status_code == 409
    assert boss.post(f"/staff/{boss.id}/reset-mfa").status_code == 409


def test_passwords(client, boss, hire):
    s = hire("finance")
    assert s.post("/auth/change-password", json={"current_password": "nope", "new_password": "another-long-one"}).status_code == 422
    assert s.post("/auth/change-password", json={"current_password": s.password, "new_password": "another-long-one"}).status_code == 204
    assert client.post("/auth/forgot-password", json={"email": "nobody@nowhere.example"}).status_code == 202
    assert client.post("/auth/forgot-password", json={"email": s.email}).status_code == 202
    t = token_from(OUTBOX[-1])
    assert client.get(f"/auth/password-link/{t}").json()["purpose"] == "reset"
    step = client.post("/auth/set-password", json={"token": t, "password": "third-long-password"}).json()
    assert step["next"] == "mfa"                             # a reset never skips two-step sign-in
    assert client.post("/auth/set-password", json={"token": t, "password": "fourth-long-password"}).status_code == 410
    codes = s.post("/auth/recovery-codes", json={"code": code(s.secret)}).json()["recovery_codes"]
    assert len(codes) == 10 and codes != s.recovery


def test_sign_in_guessing_is_limited(client, boss, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    for _ in range(10):
        client.post("/auth/login", json={"email": boss.email, "password": "guess-guess"})
    assert client.post("/auth/login", json={"email": boss.email, "password": boss.password}).status_code == 429


def test_the_crm_shares_a_database_without_touching_geohub(client, boss):
    import psycopg
    with psycopg.connect(settings.database_url) as c:
        assert [r[0] for r in c.execute("SELECT email FROM public.users")] == ["geohub@user.example"]
        assert [r[0] for r in c.execute("SELECT name FROM public.schema_migrations")] == ["001_geohub.sql"]
        crm = {r[0] for r in c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
                                       (settings.db_schema,))}
        assert {"users", "accounts", "deals", "activities", "schema_migrations"} <= crm
        assert c.execute(f"SELECT count(*) FROM {settings.db_schema}.users WHERE email = %s", (boss.email,)).fetchone()[0] == 1
