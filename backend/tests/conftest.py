"""Tests run against a real PostgreSQL (a crm_test database). Locally: see README "Running the tests"."""
import os
import re
import time
import uuid
from pathlib import Path

import pytest

env_file = Path(__file__).resolve().parent.parent / ".env.test"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from fastapi.testclient import TestClient  # noqa: E402

from app import bootstrap, mfa, ratelimit  # noqa: E402
from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import auth, staff  # noqa: E402

OUTBOX: list[dict] = []


async def _fake_send(to, subject, body, *, action=None):
    OUTBOX.append({"to": to, "subject": subject, "body": body, "action": action})
    return True


class Clock:
    """Each code asked for comes from the next 30-second step, as if time passed: a code works only once."""
    def __init__(self):
        self.t = time.time()

    def time(self):
        return self.t


CLOCK = Clock()


def code(secret: str) -> str:
    CLOCK.t += 30
    return mfa.code_now(secret, CLOCK.t)


@pytest.fixture(scope="session")
def client():
    for m in (bootstrap, auth, staff):
        m.send_email = _fake_send
    mfa.clock = CLOCK
    import psycopg
    with psycopg.connect(settings.database_url, autocommit=True) as c:      # a clean database each run
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def fresh_limits():
    ratelimit.reset()
    yield


def uid() -> str:
    return uuid.uuid4().hex[:8]


def token_from(mail: dict) -> str:
    return re.search(r"token=([\w-]+)", mail["action"][1]).group(1)


class Staff:
    """A signed-in staff member: password chosen from the emailed link, two-step sign-in set up."""
    def __init__(self, client, email: str, password: str = "a-long-staff-password"):
        self.c, self.email, self.password = client, email, password
        mail = next(m for m in reversed(OUTBOX) if m["to"] == email and m["action"] and "set-password" in m["action"][1])
        step = client.post("/auth/set-password", json={"token": token_from(mail), "password": password}).json()
        assert step["next"] == "enroll", step
        setup = client.post("/auth/enroll/start", json={"token": step["token"]}).json()
        self.secret = setup["secret"]
        done = client.post("/auth/enroll/finish", json={"token": step["token"], "code": code(self.secret)})
        assert done.status_code == 200, done.text
        self.session = done.json()
        self.recovery = self.session["recovery_codes"]
        self.id = self.session["user"]["id"]
        self.h = {"Authorization": f"Bearer {self.session['access_token']}"}

    def get(self, url, **kw): return self.c.get(url, headers=self.h, **kw)
    def post(self, url, **kw): return self.c.post(url, headers=self.h, **kw)
    def patch(self, url, **kw): return self.c.patch(url, headers=self.h, **kw)
    def delete(self, url, **kw): return self.c.delete(url, headers=self.h, **kw)


@pytest.fixture(scope="session")
def boss(client):
    """The super admin made on start-up from SUPER_ADMIN_EMAIL."""
    return Staff(client, settings.super_admin_email)


@pytest.fixture
def hire(client, boss):
    def make(role="account_manager", name="Staff Member"):
        email = f"{uid()}@geoestate.example"
        r = boss.post("/staff", json={"email": email, "name": name, "role": role})
        assert r.status_code == 201, r.text
        return Staff(client, email)
    return make
