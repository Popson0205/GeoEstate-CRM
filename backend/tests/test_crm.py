from datetime import datetime, timedelta, timezone

from conftest import uid


def test_clients_and_contacts(client, boss, hire):
    am = hire("account_manager", "Funke Ola")
    support = hire("support")
    finance = hire("finance")
    name = f"Lagos Survey {uid()}"
    r = am.post("/accounts", json={"name": f"  {name} ", "industry": "Surveying", "city": "Lagos", "state": "Lagos"})
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["name"] == name and a["status"] == "lead" and a["owner_name"] == "Funke Ola" and a["country"] == "Nigeria"
    assert support.post("/accounts", json={"name": "Not allowed"}).status_code == 403
    assert finance.patch(f"/accounts/{a['id']}", json={"status": "customer"}).status_code == 403

    # contacts: support may add them; one is the main contact
    c1 = support.post(f"/accounts/{a['id']}/contacts", json={"name": "Ada Obi", "title": "MD", "email": " ADA@LagosSurvey.example ",
                                                            "is_primary": True}).json()
    assert c1["email"] == "ada@lagossurvey.example"
    c2 = am.post(f"/accounts/{a['id']}/contacts", json={"name": "Bola Ade", "is_primary": True}).json()
    d = finance.get(f"/accounts/{a['id']}").json()
    assert [c["name"] for c in d["contacts"]] == ["Bola Ade", "Ada Obi"] and d["primary_contact"] == "Bola Ade"
    assert am.patch(f"/contacts/{c1['id']}", json={"phone": "+234 803 000 0000"}).json()["phone"] == "+234 803 000 0000"
    assert finance.delete(f"/contacts/{c2['id']}").status_code == 403
    assert am.delete(f"/contacts/{c2['id']}").status_code == 204

    # find by name, city or a contact's email
    for q in (name[:12], "lagossurvey.example"):
        assert a["id"] in [x["id"] for x in finance.get("/accounts", params={"q": q}).json()]
    assert am.patch(f"/accounts/{a['id']}", json={"owner_id": finance.id, "notes": "Met at GeoSummit"}).json()["owner_name"]
    assert am.patch(f"/accounts/{a['id']}", json={"owner_id": "00000000-0000-0000-0000-000000000000"}).status_code == 422
    # only super admins delete clients
    assert am.delete(f"/accounts/{a['id']}").status_code == 403


def test_the_pipeline(client, boss, hire):
    am = hire("account_manager", "Deal Maker")
    a = am.post("/accounts", json={"name": f"Kaduna Land Agency {uid()}"}).json()
    deal = am.post("/deals", json={"account_id": a["id"], "title": "Organization Advanced, first year", "plan": "advanced",
                                   "amount_ngn": "1500000.00", "expected_close": "2026-12-15"})
    assert deal.status_code == 201, deal.text
    d = deal.json()
    assert d["stage"] == "new" and d["owner_name"] == "Deal Maker" and d["account_name"] == a["name"] and float(d["amount_ngn"]) == 1500000
    assert am.post("/deals", json={"account_id": a["id"], "title": "x", "stage": "lost"}).status_code == 422

    for stage in ("contacted", "demo", "proposal"):
        assert am.patch(f"/deals/{d['id']}", json={"stage": stage}).json()["stage"] == stage
    lost = am.patch(f"/deals/{d['id']}", json={"stage": "lost"})
    assert lost.status_code == 422 and "why" in lost.json()["detail"]
    won = am.patch(f"/deals/{d['id']}", json={"stage": "won"}).json()
    assert won["closed_at"] is not None
    assert am.get(f"/accounts/{a['id']}").json()["status"] == "customer"         # a win makes it a customer
    reopened = am.patch(f"/deals/{d['id']}", json={"stage": "proposal"}).json()
    assert reopened["closed_at"] is None
    assert am.patch(f"/deals/{d['id']}", json={"stage": "lost", "lost_reason": "Chose another vendor"}).json()["lost_reason"] == "Chose another vendor"

    other = am.post("/deals", json={"account_id": a["id"], "title": "Custom server", "plan": "custom", "amount_ngn": 500000}).json()
    open_ = am.get("/deals", params={"stage": "open"}).json()
    assert other["id"] in [x["id"] for x in open_] and d["id"] not in [x["id"] for x in open_]
    acc = am.get("/accounts", params={"q": a["name"]}).json()[0]
    assert acc["open_deals"] == 1 and float(acc["open_value_ngn"]) == 500000
    assert am.patch(f"/deals/{other['id']}", json={"clear_amount": True}).json()["amount_ngn"] is None
    assert am.delete(f"/deals/{other['id']}").status_code == 403
    assert boss.delete(f"/deals/{other['id']}").status_code == 204


def test_tasks_and_logged_activity(client, boss, hire):
    am = hire("account_manager", "Task Giver")
    support = hire("support", "Task Doer")
    a = am.post("/accounts", json={"name": f"Ogun Farms {uid()}"}).json()
    deal = am.post("/deals", json={"account_id": a["id"], "title": "Standard"}).json()
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    late = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    t1 = am.post("/activities", json={"kind": "task", "subject": "Send the proposal", "due_at": soon, "deal_id": deal["id"],
                                      "owner_id": support.id}).json()
    assert t1["owner_name"] == "Task Doer" and t1["account_id"] == a["id"] and t1["done_at"] is None and t1["deal_title"] == "Standard"
    t2 = support.post("/activities", json={"subject": "Call Ada back", "due_at": late, "account_id": a["id"]}).json()
    note = support.post("/activities", json={"kind": "note", "subject": "Wants 20 more collectors", "account_id": a["id"]}).json()
    call = support.post("/activities", json={"kind": "call", "subject": "Spoke to Ada", "account_id": a["id"], "done": True}).json()
    assert note["done_at"] is not None and call["done_at"] is not None

    mine = [x["subject"] for x in support.get("/activities", params={"mine": True}).json()]
    assert mine[:2] == ["Call Ada back", "Send the proposal"]                     # soonest first
    assert [x["subject"] for x in support.get("/activities", params={"mine": True, "due": "overdue"}).json()] == ["Call Ada back"]
    home = support.get("/home").json()
    assert home["my_open_tasks"] == 2 and home["my_overdue"] == 1 and home["my_tasks"][0]["subject"] == "Call Ada back"
    assert any(x["subject"] == "Spoke to Ada" for x in home["recent"])

    done = support.patch(f"/activities/{t2['id']}", json={"done": True}).json()
    assert done["done_at"] is not None
    assert support.patch(f"/activities/{t2['id']}", json={"done": False}).json()["done_at"] is None
    assert support.patch(f"/activities/{t1['id']}", json={"clear_due": True}).json()["due_at"] is None
    # the client's page shows open tasks first, then what happened
    acts = support.get(f"/accounts/{a['id']}").json()["activities"]
    assert {x["subject"] for x in acts} == {"Send the proposal", "Call Ada back", "Wants 20 more collectors", "Spoke to Ada"}
    assert acts[0]["done_at"] is None
    # only its author or a super admin deletes it
    assert support.delete(f"/activities/{t1['id']}").status_code == 403
    assert am.delete(f"/activities/{t1['id']}").status_code == 204


def test_home_and_the_activity_log(client, boss, hire):
    am = hire("account_manager")
    finance = hire("finance")
    a = am.post("/accounts", json={"name": f"Kano Trial {uid()}"}).json()
    d = am.post("/deals", json={"account_id": a["id"], "title": "Advanced", "plan": "advanced", "amount_ngn": 1000000, "stage": "proposal"}).json()
    home = am.get("/home").json()
    proposal = next(s for s in home["pipeline"] if s["stage"] == "proposal")
    assert proposal["count"] >= 1 and float(proposal["value_ngn"]) >= 1000000
    before = float(home["won_this_month_ngn"])
    am.patch(f"/deals/{d['id']}", json={"stage": "won"})
    assert float(am.get("/home").json()["won_this_month_ngn"]) == before + 1000000

    assert am.get("/audit").status_code == 403
    log = finance.get("/audit").json()
    moves = [e for e in log if e["action"] == "deal.move" and e["target_id"] == d["id"]]
    assert moves and moves[0]["details"] == {"from": "proposal", "to": "won", "title": "Advanced"} and moves[0]["actor_name"]
    assert any(e["action"] == "staff.add" for e in boss.get("/audit", params={"limit": 200}).json())
