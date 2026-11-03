"""A stand-in for Geohub's /crm-link API, kept in memory."""
import json
import uuid
from datetime import date, datetime, timezone

import httpx

KEY = "a-crm-link-key-that-is-long-enough-0123456789"
URL = "https://geohub.test"


class FakeGeohub:
    def __init__(self):
        self.orgs: dict[str, dict] = {}
        self.requests: list[dict] = []
        self.calls: list[tuple[str, str, dict | None]] = []
        self.down = False

    def org(self, name, plan="standard", kind="paid", ends=None, status="active", owner=("Ada Obi", "ada@client.example")):
        oid = str(uuid.uuid4())
        self.orgs[oid] = {"id": oid, "name": name, "plan": plan, "plan_name": f"Organization {plan.title()}", "licence_kind": kind,
                          "status": status, "status_name": status.title(), "subscription_starts": None,
                          "subscription_ends": ends.isoformat() if ends else None, "grace_ends": None, "suspended_reason": None,
                          "owner_name": owner[0], "owner_email": owner[1], "created_at": datetime.now(timezone.utc).isoformat(),
                          "last_active": None, "console_url": f"{URL}/admin/customers/{oid}", "already_applied": False,
                          "refs": set(), "products": [{"product": "hub", "plan": plan, "status": status}]}
        return self.orgs[oid]

    def request(self, organization, plan="standard", **kw):
        r = {"id": str(uuid.uuid4()), "organization": organization, "contact_name": kw.get("contact_name", "Bola Ade"),
             "email": kw.get("email", "bola@lead.example"), "phone": kw.get("phone"), "plan": plan, "team_size": kw.get("team_size"),
             "message": kw.get("message"), "status": "new", "org_id": None, "created_at": datetime.now(timezone.utc).isoformat()}
        self.requests.append(r)
        return r

    @staticmethod
    def _public(o):
        return {k: v for k, v in o.items() if k != "refs"}

    def handle(self, req: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("down")
        body = json.loads(req.content) if req.content else None
        path = req.url.path.removeprefix("/api/crm-link")
        self.calls.append((req.method, path, body))
        if req.headers.get("authorization") != f"Bearer {KEY}":
            return httpx.Response(401, json={"detail": "bad key"})
        if req.method == "GET" and path == "/orgs":
            ids = req.url.params.get("ids")
            items = [o for o in self.orgs.values() if not ids or o["id"] in ids.split(",")]
            return httpx.Response(200, json=[self._public(o) for o in items])
        if req.method == "GET" and path == "/requests":
            return httpx.Response(200, json=self.requests)
        if req.method == "POST" and path == "/orgs":
            o = self.org(body["name"], plan=body.get("plan", "standard") if body["licence_kind"] == "paid" else "advanced",
                         kind=body["licence_kind"], status="demo" if body["licence_kind"] == "demo" else "active",
                         owner=(body["owner_name"], body["owner_email"]))
            if body.get("invoice_ref"):
                o["refs"].add(f"hub/{body['invoice_ref']}")
                o["subscription_ends"] = body["subscription_ends"]
            return httpx.Response(201, json=self._public(o))
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "orgs":
            o = self.orgs.get(parts[1])
            if not o:
                return httpx.Response(404, json={"detail": "That organization is not on Geohub (any more)."})
            if req.method == "GET":
                return httpx.Response(200, json=self._public(o))
            if parts[2:] == ["licence"]:
                key = f"{body.get('product', 'hub')}/{body['invoice_ref']}"
                if key in o["refs"]:
                    return httpx.Response(200, json=self._public(o) | {"already_applied": True})
                o["refs"].add(key)
                if body.get("product", "hub") != "hub":
                    o["products"] = [p for p in o["products"] if p["product"] != body["product"]] + [
                        {"product": body["product"], "plan": body["plan"], "status": "active", "subscription_ends": body["subscription_ends"]}]
                    return httpx.Response(200, json=self._public(o))
                o.update(plan=body["plan"], licence_kind="paid", subscription_starts=body["subscription_starts"],
                         subscription_ends=body["subscription_ends"],
                         status="active" if o["status"] != "suspended" or body["lift_suspension"] else "suspended")
                return httpx.Response(200, json=self._public(o))
        return httpx.Response(404, json={"detail": "Not found."})
