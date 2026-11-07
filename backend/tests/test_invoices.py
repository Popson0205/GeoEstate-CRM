from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest

from app import geohub, invoicing
from app.config import settings
from conftest import OUTBOX, uid
from fake_geohub import KEY, URL, FakeGeohub

YEAR = date.today().year


@pytest.fixture
def hub(monkeypatch):
    g = FakeGeohub()
    monkeypatch.setattr(settings, "geohub_url", URL)
    monkeypatch.setattr(settings, "geohub_link_key", KEY)
    monkeypatch.setattr(geohub, "transport", httpx.MockTransport(g.handle))
    return g


def client_with_contact(am, name="Ada Obi", email="ada@client.example"):
    a = am.post("/accounts", json={"name": f"Lagos Survey {uid()}", "address": "12 Marina Road", "city": "Lagos",
                                   "state": "Lagos", "tin": "1234567-0001"}).json()
    am.post(f"/accounts/{a['id']}/contacts", json={"name": name, "title": "MD", "email": email, "is_primary": True})
    return a


def lic(plan="standard", start=None):
    s = start or date.today()
    return {"licence_plan": plan, "licence_starts": s.isoformat(), "licence_ends": (s + timedelta(days=364)).isoformat()}


def test_money_numbers_and_words():
    t = invoicing.totals([{"quantity": 1, "unit_price_ngn": 750000}], 7.5)
    assert t["subtotal_ngn"] == Decimal("750000.00") and t["vat_ngn"] == Decimal("56250.00") and t["total_ngn"] == Decimal("806250.00")
    t = invoicing.totals([{"quantity": "3", "unit_price_ngn": "333.33"}, {"quantity": "0.5", "unit_price_ngn": "0.05"}], 7.5)
    assert t["amounts"] == [Decimal("999.99"), Decimal("0.03")] and t["vat_ngn"] == Decimal("75.00")
    assert invoicing.naira_words(Decimal("806250")) == "Eight hundred and six thousand, two hundred and fifty naira only" \
        or invoicing.naira_words(Decimal("806250")) == "Eight hundred and six thousand two hundred and fifty naira only"
    assert invoicing.naira_words(Decimal("1612500.50")) == \
        "One million six hundred and twelve thousand five hundred naira, fifty kobo only"
    assert invoicing.naira_words(Decimal("1000005")) == "One million and five naira only"
    assert invoicing.licence_dates(None, date(2026, 11, 3)) == (date(2026, 11, 3), date(2027, 11, 2))
    assert invoicing.licence_dates(date(2027, 1, 31), date(2026, 11, 3)) == (date(2027, 2, 1), date(2028, 1, 31))
    assert invoicing.licence_dates(date(2026, 1, 1), date(2026, 11, 3))[0] == date(2026, 11, 3)      # lapsed: from today


def test_prices(client, boss, hire):
    am = hire("account_manager")
    p = {x["plan"]: x for x in am.get("/prices").json()}
    assert float(p["standard"]["amount_ngn"]) == 750000 and float(p["advanced"]["amount_ngn"]) == 1500000
    assert am.put("/prices/hub/standard", json={"amount_ngn": 800000}).status_code == 403
    assert float(boss.put("/prices/hub/standard", json={"amount_ngn": 800000}).json()["amount_ngn"]) == 800000
    boss.put("/prices/hub/standard", json={"amount_ngn": 750000})
    assert boss.put("/prices/gold/standard", json={"amount_ngn": 1}).status_code == 422
    # other products get their own prices
    land = boss.put("/prices/land/standard", json={"amount_ngn": 2500000}).json()
    assert land["product"] == "land" and land["name"] == "Land Registry Standard"
    assert [(x["product"], x["plan"]) for x in am.get("/prices").json()] == [("hub", "standard"), ("hub", "advanced"), ("land", "standard")]
    assert boss.delete("/prices/land/standard").status_code == 204 and boss.delete("/prices/land/standard").status_code == 404
    c = am.get("/company").json()
    assert c["rc"] == "9631300" and c["tin"] == "2623706767701" and c["bank_account_number"] == "3005285279" and c["vat_rate"] == 7.5


def test_an_invoice_from_draft_to_paid(client, boss, hire, hub):
    am, fin, sup = hire("account_manager", "Funke Ola"), hire("finance", "Femi Cash"), hire("support")
    a = client_with_contact(am)
    deal = am.post("/deals", json={"account_id": a["id"], "title": "Standard, first year", "stage": "proposal"}).json()
    body = {"account_id": a["id"], "deal_id": deal["id"], "notes": "Thank you for choosing Geohub.",
            "lines": [{"description": "Geohub Organization Standard licence, one year", "unit_price_ngn": 750000}], **lic()}
    assert sup.post("/invoices", json=body).status_code == 403
    r = am.post("/invoices", json=body)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["status"] == "draft" and d["number"] is None and float(d["vat_ngn"]) == 56250 and float(d["total_ngn"]) == 806250
    assert float(d["balance_ngn"]) == 0 and d["bill_to"]["contact"] == "Ada Obi, MD" and d["bill_to"]["tin"] == "1234567-0001"
    assert am.post(f"/invoices/{d['id']}/payments", json={"amount_ngn": 1, "paid_on": date.today().isoformat()}).status_code == 403
    assert fin.post(f"/invoices/{d['id']}/payments", json={"amount_ngn": 1, "paid_on": date.today().isoformat()}).status_code == 409
    assert am.post(f"/invoices/{d['id']}/email", json={}).status_code == 409

    # drafts change freely
    two = am.patch(f"/invoices/{d['id']}", json={"lines": body["lines"] + [{"description": "Training day", "quantity": 2,
                                                                             "unit_price_ngn": "50000"}]}).json()
    assert float(two["subtotal_ngn"]) == 850000 and float(two["total_ngn"]) == 913750 and len(two["lines"]) == 2
    assert am.patch(f"/invoices/{d['id']}", json={"licence_ends": "2000-01-01"}).status_code == 422
    am.patch(f"/invoices/{d['id']}", json={"lines": body["lines"]})

    # issuing gives the next number of the year and keeps the client's details as they were
    first = am.post(f"/invoices/{d['id']}/issue", json={}).json()
    assert first["number"].startswith(f"GE-{YEAR}-") and first["status"] == "issued"
    assert first["due_date"] == (date.today() + timedelta(days=14)).isoformat() and float(first["balance_ngn"]) == 806250
    am.patch(f"/accounts/{a['id']}", json={"name": "Renamed Ltd"})
    assert am.get(f"/invoices/{d['id']}").json()["bill_to"]["name"] == a["name"]
    assert am.patch(f"/invoices/{d['id']}", json={"notes": "x"}).status_code == 409
    assert am.delete(f"/invoices/{d['id']}").status_code == 409
    n = int(first["number"][-4:])
    other = am.post("/invoices", json={"account_id": a["id"], "lines": [{"description": "Support", "unit_price_ngn": 1000}]}).json()
    assert am.post(f"/invoices/{other['id']}/issue", json={}).json()["number"] == f"GE-{YEAR}-{n + 1:04d}"

    # the PDF, and the email with it attached
    pdf = am.get(f"/invoices/{d['id']}/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content[:5] == b"%PDF-"
    assert first["number"] in pdf.headers["content-disposition"]
    sent = am.post(f"/invoices/{d['id']}/email", json={"message": "Call me with any questions."}).json()
    assert sent["emailed_to"] == "ada@client.example"
    mail = OUTBOX[-1]
    assert mail["to"] == "ada@client.example" and first["number"] in mail["subject"] and "3005285279" in mail["body"]
    assert mail["attachments"][0][0] == f"{first['number']}.pdf" and mail["attachments"][0][1][:5] == b"%PDF-"

    # payments: part, too much, then the rest; paying in full wins the deal and needs Geohub
    today = date.today().isoformat()
    assert fin.post(f"/invoices/{d['id']}/payments", json={"amount_ngn": 900000, "paid_on": today}).status_code == 422
    assert fin.post(f"/invoices/{d['id']}/payments", json={"amount_ngn": 10, "paid_on": "2999-01-01"}).status_code == 422
    part = fin.post(f"/invoices/{d['id']}/payments", json={"amount_ngn": 400000, "paid_on": today, "reference": "GTB-1"}).json()
    assert part["status"] == "issued" and float(part["balance_ngn"]) == 406250 and float(part["paid_ngn"]) == 400000
    paid = fin.post(f"/invoices/{d['id']}/payments", json={"amount_ngn": "406250.00", "paid_on": today}).json()
    assert paid["status"] == "paid" and float(paid["balance_ngn"]) == 0 and paid["paid_at"]
    assert paid["licence_applied_at"] is None and "not linked to Geohub" in paid["licence_error"]
    assert am.get(f"/deals?stage=won").status_code == 200
    acc = am.get(f"/accounts/{a['id']}").json()
    assert acc["status"] == "customer" and next(x for x in acc["deals"] if x["id"] == deal["id"])["stage"] == "won"
    assert [i["number"] for i in acc["invoices"]][:2] != [] and any(i["status"] == "paid" for i in acc["invoices"])

    # set it up on Geohub from the paid invoice: the licence comes from the invoice
    contact = acc["contacts"][0]
    s = am.post(f"/accounts/{a['id']}/geohub/setup", json={"kind": "paid", "contact_id": contact["id"], "invoice_id": d["id"]})
    assert s.status_code == 201, s.text
    org = s.json()["org"]
    assert org["licence_kind"] == "paid" and org["owner_email"] == "ada@client.example"
    assert hub.calls[-1][2]["invoice_ref"] == first["number"] and hub.calls[-1][2]["staff_name"] == "Funke Ola"
    assert am.get(f"/invoices/{d['id']}").json()["licence_applied_at"] is not None
    assert am.get(f"/accounts/{a['id']}/geohub").json()["org"]["id"] == org["id"]

    home = fin.get("/home").json()
    assert float(home["received_this_month_ngn"]) >= 806250 and float(home["unpaid_ngn"]) >= 1075

    # removing a payment re-opens the invoice
    pid = paid["payments"][-1]["id"]
    assert am.delete(f"/payments/{pid}").status_code == 403
    back = fin.delete(f"/payments/{pid}").json()
    assert back["status"] == "issued" and float(back["balance_ngn"]) == 406250
    assert fin.post(f"/invoices/{d['id']}/void", json={"reason": "x"}).status_code == 409        # has payments
    log = boss.get("/audit").json()
    assert {"payment.record", "payment.delete", "invoice.issue", "invoice.email", "geohub.setup"} <= {e["action"] for e in log}


def test_renewal_switches_the_licence_on_and_void(client, boss, hire, hub):
    am, fin = hire("account_manager"), hire("finance", "Femi Cash")
    org = hub.org("Kano Agency", ends=date.today() + timedelta(days=20))
    a = client_with_contact(am)
    assert am.put(f"/accounts/{a['id']}/geohub", json={"org_id": org["id"]}).json()["org"]["name"] == "Kano Agency"
    b = client_with_contact(am)
    assert am.put(f"/accounts/{b['id']}/geohub", json={"org_id": org["id"]}).status_code == 409   # one client per organization
    assert am.put(f"/accounts/{b['id']}/geohub", json={"org_id": "00000000-0000-0000-0000-000000000000"}).status_code == 404

    start, _ = invoicing.licence_dates(date.today() + timedelta(days=20))
    inv = am.post("/invoices", json={"account_id": a["id"], "lines": [{"description": "Advanced", "unit_price_ngn": 1500000}],
                                     **lic("advanced", start)}).json()
    inv = am.post(f"/invoices/{inv['id']}/issue", json={}).json()
    assert float(inv["total_ngn"]) == 1612500
    hub.down = True
    paid = fin.post(f"/invoices/{inv['id']}/payments", json={"amount_ngn": 1612500, "paid_on": date.today().isoformat(),
                                                             "reference": "GTB-77"}).json()
    assert paid["status"] == "paid" and "did not answer" in paid["licence_error"]             # the payment is kept
    hub.down = False
    again = fin.post(f"/invoices/{inv['id']}/licence").json()
    assert again["licence_applied_at"] and again["licence_error"] is None
    assert org["plan"] == "advanced" and org["subscription_ends"] == (start + timedelta(days=364)).isoformat()
    assert hub.calls[-1][2]["invoice_ref"] == inv["number"]

    # void: only issued, unpaid invoices; the number is kept
    x = am.post("/invoices", json={"account_id": a["id"], "lines": [{"description": "Mistake", "unit_price_ngn": 5}]}).json()
    assert fin.post(f"/invoices/{x['id']}/void", json={"reason": "wrong"}).status_code == 409
    x = am.post(f"/invoices/{x['id']}/issue", json={}).json()
    assert am.post(f"/invoices/{x['id']}/void", json={"reason": "wrong"}).status_code == 403
    v = fin.post(f"/invoices/{x['id']}/void", json={"reason": "Wrong client"}).json()
    assert v["status"] == "void" and v["number"] and float(v["balance_ngn"]) == 0
    assert fin.post(f"/invoices/{x['id']}/payments", json={"amount_ngn": 1, "paid_on": date.today().isoformat()}).status_code == 409
    assert am.get(f"/invoices/{x['id']}/pdf").status_code == 200
    # a client with issued invoices is kept
    assert boss.delete(f"/accounts/{a['id']}").status_code == 409
    d = am.post("/invoices", json={"account_id": b["id"], "lines": [{"description": "x", "unit_price_ngn": 5}]}).json()
    assert boss.delete(f"/accounts/{b['id']}").status_code == 204
    assert am.get(f"/invoices/{d['id']}").status_code == 404

    lists = {s: [i["id"] for i in am.get("/invoices", params={"status": s}).json()] for s in ("paid", "void", "unpaid")}
    assert inv["id"] in lists["paid"] and x["id"] in lists["void"] and inv["id"] not in lists["unpaid"]
    assert inv["id"] in [i["id"] for i in am.get("/invoices", params={"q": inv["number"]}).json()]


def test_geohub_customers_and_requests_come_into_the_crm(client, boss, hire, hub, monkeypatch):
    am, sup = hire("account_manager", "Funke Ola"), hire("support")
    o1 = hub.org(f"Abuja Lands {uid()}", ends=date.today() + timedelta(days=200))
    o2 = hub.org(f"Old Client {uid()}", status="expired", owner=("Chika Eze", "chika@old.example"))
    r1 = hub.request(f"Survey Co {uid()}", plan="demo", contact_name="Bola Ade", email="bola@lead.example", team_size="10",
                     message="We map farms.")
    listed = {o["id"]: o for o in sup.get("/geohub/orgs").json()}
    assert listed[o1["id"]]["crm_account_id"] is None
    assert sup.post("/geohub/import", json={"org_ids": [o1["id"]]}).status_code == 403
    r = am.post("/geohub/import", json={"org_ids": [o1["id"], o2["id"]], "request_ids": [r1["id"]]}).json()
    assert r["added"] == 3 and r["skipped"] == 0
    assert am.post("/geohub/import", json={"org_ids": [o1["id"]], "request_ids": [r1["id"]]}).json() == {"added": 0, "skipped": 2, "accounts": []}

    listed = {o["id"]: o for o in sup.get("/geohub/orgs").json()}
    a1 = am.get(f"/accounts/{listed[o1['id']]['crm_account_id']}").json()
    assert a1["status"] == "customer" and a1["contacts"][0]["email"] == "ada@client.example" and a1["geohub_org_id"] == o1["id"]
    assert am.get(f"/accounts/{listed[o2['id']]['crm_account_id']}").json()["status"] == "former"
    req = next(x for x in sup.get("/geohub/requests").json() if x["id"] == r1["id"])
    lead = am.get(f"/accounts/{req['crm_account_id']}").json()
    assert lead["status"] == "lead" and lead["contacts"][0]["name"] == "Bola Ade" and lead["deals"][0]["plan"] == "demo"
    assert "We map farms." in lead["deals"][0]["notes"] and lead["activities"][0]["subject"].startswith("Contact Bola Ade")

    # a month's demo, set up from the CRM
    demo = am.post(f"/accounts/{lead['id']}/geohub/setup", json={"kind": "demo", "contact_id": lead["contacts"][0]["id"]})
    assert demo.status_code == 201 and demo.json()["org"]["status"] == "demo"
    assert hub.calls[-1][2]["request_id"] == r1["id"] and hub.calls[-1][2]["licence_kind"] == "demo"
    assert am.post(f"/accounts/{lead['id']}/geohub/setup", json={"kind": "demo", "contact_id": lead["contacts"][0]["id"]}).status_code == 409
    after = am.get(f"/accounts/{lead['id']}").json()
    assert any(t["subject"].startswith("Demo ends") for t in after["activities"]) and after["deals"][0]["stage"] == "demo"
    assert am.delete(f"/accounts/{lead['id']}/geohub").status_code == 204
    assert am.get(f"/accounts/{lead['id']}/geohub").json() == {"org": None, "error": None}

    # Geohub's answers, in words staff can act on
    monkeypatch.setattr(settings, "geohub_link_key", "wrong-key")
    r = sup.get("/geohub/orgs")
    assert r.status_code == 502 and "GEOHUB_LINK_KEY" in r.json()["detail"]
    monkeypatch.setattr(settings, "geohub_url", "")
    assert sup.get("/geohub").json()["linked"] is False
    assert "not linked to Geohub yet" in sup.get("/geohub/orgs").json()["detail"]


def test_an_invoice_for_another_product(client, boss, hire, hub):
    am, fin = hire("account_manager"), hire("finance", "Femi Cash")
    org = hub.org("Abuja Lands Bureau", ends=date.today() + timedelta(days=200))
    a = client_with_contact(am)
    am.put(f"/accounts/{a['id']}/geohub", json={"org_id": org["id"]})
    s = date.today()
    inv = am.post("/invoices", json={"account_id": a["id"], "lines": [{"description": "Land Registry Standard licence", "unit_price_ngn": 2500000}],
                                     "licence_product": "land", **lic("standard", s)}).json()
    assert inv["licence_product"] == "land"
    assert am.patch(f"/invoices/{inv['id']}", json={"licence_product": "farm"}).json()["licence_product"] == "farm"
    am.patch(f"/invoices/{inv['id']}", json={"licence_product": "land"})
    inv = am.post(f"/invoices/{inv['id']}/issue", json={}).json()
    pdf = am.get(f"/invoices/{inv['id']}/pdf")
    assert pdf.status_code == 200
    paid = fin.post(f"/invoices/{inv['id']}/payments", json={"amount_ngn": inv["total_ngn"], "paid_on": date.today().isoformat()}).json()
    assert paid["licence_applied_at"] and hub.calls[-1][2]["product"] == "land" and hub.calls[-1][2]["invoice_ref"] == inv["number"]
    assert any(p["product"] == "land" for p in org["products"])
    # a client not yet on Geohub cannot be set up from a Land Registry invoice
    b = client_with_contact(am)
    x = am.post("/invoices", json={"account_id": b["id"], "lines": [{"description": "Land", "unit_price_ngn": 10}], "licence_product": "land", **lic()}).json()
    x = am.post(f"/invoices/{x['id']}/issue", json={}).json()
    fin.post(f"/invoices/{x['id']}/payments", json={"amount_ngn": x["total_ngn"], "paid_on": date.today().isoformat()})
    contact = am.get(f"/accounts/{b['id']}").json()["contacts"][0]
    r = am.post(f"/accounts/{b['id']}/geohub/setup", json={"kind": "paid", "contact_id": contact["id"], "invoice_id": x["id"]})
    assert r.status_code == 409 and "set it up on Geohub first" in r.json()["detail"]


def test_several_products_on_one_invoice(client, boss, hire, hub):
    """Geohub, FarmScan and LandCheck on one invoice with a training line: each licence is switched on when it is paid,
    Geohub's first, and a client set up on Geohub from the invoice gets the others straight after."""
    am, fin = hire("account_manager"), hire("finance", "Femi Cash")
    a = client_with_contact(am)
    s = date.today()

    def line(product, plan, price, desc=None):
        return {"description": desc or f"{product} {plan}", "unit_price_ngn": price, "licence_product": product, **lic(plan, s)}
    lines = [line("farm", "advanced", 1200000), line("hub", "standard", 750000), line("check", "standard", 300000),
             {"description": "Training, two days on site", "quantity": 2, "unit_price_ngn": 150000}]
    # a product twice, or a licence without its plan, is refused
    bad = am.post("/invoices", json={"account_id": a["id"], "lines": lines + [line("farm", "standard", 1)]})
    assert bad.status_code == 422 and "twice" in bad.json()["detail"]
    half = {"description": "x", "unit_price_ngn": 1, "licence_product": "land"}
    assert am.post("/invoices", json={"account_id": a["id"], "lines": [half]}).status_code == 422

    inv = am.post("/invoices", json={"account_id": a["id"], "lines": lines}).json()
    assert float(inv["subtotal_ngn"]) == 2550000 and inv["licence_products"] == ["farm", "hub", "check"]
    assert inv["licence_product"] == "hub"                        # the summary is the Geohub licence
    assert [l["licence_product"] for l in inv["lines"]] == ["farm", "hub", "check", None]
    # removing one product from the draft keeps the others
    kept = am.patch(f"/invoices/{inv['id']}", json={"lines": [lines[0], lines[1], lines[3]]}).json()
    assert kept["licence_products"] == ["farm", "hub"]
    inv = am.post(f"/invoices/{inv['id']}/issue", json={}).json()
    assert am.get(f"/invoices/{inv['id']}/pdf").status_code == 200

    # paid before the client is on Geohub: nothing can be switched on yet, and the payment is kept
    paid = fin.post(f"/invoices/{inv['id']}/payments", json={"amount_ngn": inv["total_ngn"], "paid_on": date.today().isoformat()}).json()
    assert paid["status"] == "paid" and paid["licence_applied_at"] is None and "not linked to Geohub" in paid["licence_error"]
    # set up on Geohub from the invoice: Geohub's licence makes the organization, then FarmScan is added to it
    contact = am.get(f"/accounts/{a['id']}").json()["contacts"][0]
    r = am.post(f"/accounts/{a['id']}/geohub/setup", json={"kind": "paid", "contact_id": contact["id"], "invoice_id": inv["id"]})
    assert r.status_code == 201, r.text
    assert hub.calls[-1][2]["product"] == "farm" and hub.calls[-1][2]["plan"] == "advanced"
    done = am.get(f"/invoices/{inv['id']}").json()
    assert done["licence_applied_at"] and done["licence_error"] is None
    assert all(l["licence_applied_at"] for l in done["lines"] if l["licence_product"])


def test_terms_print_on_every_invoice_and_issued_ones_keep_theirs(client, boss, hire):
    am = hire("account_manager")
    t = am.get("/invoice-terms").json()
    assert "Validity" in t["body"] and "{due_date}" in t["body"]
    assert am.put("/invoice-terms", json={"body": "Pay on time."}).status_code == 403          # super admins only
    a = client_with_contact(am)
    d = am.post("/invoices", json={"account_id": a["id"], "lines": [{"description": "Training", "unit_price_ngn": 100000}]}).json()
    assert d["terms"] == t["body"]                                                              # a draft shows today's terms
    issued = am.post(f"/invoices/{d['id']}/issue", json={}).json()
    assert issued["terms"] == t["body"]
    with_terms = am.get(f"/invoices/{d['id']}/pdf")
    # new terms apply to drafts and invoices issued from now on; the one already sent keeps the terms it went out with
    r = boss.put("/invoice-terms", json={"body": "  1. Pay by {due_date}.  \n2. Quote {number}.\n"})
    assert r.status_code == 200 and r.json()["body"] == "1. Pay by {due_date}.\n2. Quote {number}." and r.json()["updated_by_name"]
    assert am.get(f"/invoices/{d['id']}").json()["terms"] == t["body"]
    d2 = am.post("/invoices", json={"account_id": a["id"], "lines": [{"description": "Training", "unit_price_ngn": 1}]}).json()
    assert d2["terms"].startswith("1. Pay by")
    assert with_terms.status_code == 200 and len(with_terms.content) > len(am.get(f"/invoices/{d2['id']}/pdf").content)
    assert any(e["action"] == "terms.update" for e in boss.get("/audit").json())
