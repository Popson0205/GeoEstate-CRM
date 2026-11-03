"""Invoices in naira with VAT, their PDF and email, payments received by bank transfer, and the price list.

draft (editable, no number) -> issued (numbered GE-2026-0001, can be emailed, takes payments) -> paid
An issued invoice with no payments can be voided; it keeps its number. Paying in full switches on its Geohub licence."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from .. import invoicing, pdf
from ..audit import audit
from ..config import settings
from ..db import get_conn
from ..deps import current_user, require
from ..errors import Problem
from ..mailer import send_email
from ..schemas import (CompanyOut, EmailInvoiceIn, InvoiceDetail, InvoiceIn, InvoiceOut, InvoicePatch, IssueIn, PaymentIn,
                       PaymentOut, PriceIn, PriceOut, VoidIn)

router = APIRouter(tags=["invoices"])

INVOICE_SQL = (
    "SELECT i.*, a.name AS account_name, a.geohub_org_id, d.title AS deal_title, u.name AS created_by_name, "
    "  COALESCE((SELECT sum(p.amount_ngn) FROM payments p WHERE p.invoice_id = i.id), 0) AS paid_ngn, "
    "  (i.status = 'issued' AND i.due_date < current_date) AS overdue "
    "FROM invoices i JOIN accounts a ON a.id = i.account_id LEFT JOIN deals d ON d.id = i.deal_id "
    "LEFT JOIN users u ON u.id = i.created_by ")


def _shape(row: dict) -> dict:
    owed = Decimal(0) if row["status"] in ("draft", "void") else row["total_ngn"] - row["paid_ngn"]
    return {**row, "balance_ngn": max(owed, Decimal(0))}


async def _get(conn, invoice_id, lock: bool = False) -> dict:
    if lock:
        await conn.execute("SELECT 1 FROM invoices WHERE id = %s FOR UPDATE", (invoice_id,))
    cur = await conn.execute(INVOICE_SQL + "WHERE i.id = %s", (invoice_id,))
    row = await cur.fetchone()
    if not row:
        raise Problem(404, "Invoice not found.", code="not_found")
    return _shape(row)


async def _detail(conn, invoice_id) -> dict:
    inv = await _get(conn, invoice_id)
    cur = await conn.execute("SELECT id, description, quantity, unit_price_ngn, amount_ngn FROM invoice_lines "
                             "WHERE invoice_id = %s ORDER BY position", (invoice_id,))
    inv["lines"] = await cur.fetchall()
    cur = await conn.execute("SELECT p.*, u.name AS recorded_by_name FROM payments p LEFT JOIN users u ON u.id = p.recorded_by "
                             "WHERE p.invoice_id = %s ORDER BY p.paid_on, p.created_at", (invoice_id,))
    inv["payments"] = await cur.fetchall()
    if inv["status"] == "draft":                       # a draft shows the client as it is now
        inv["bill_to"] = await invoicing.bill_to(conn, inv["account_id"])
    return inv


def _draft_only(inv: dict) -> None:
    if inv["status"] != "draft":
        raise Problem(409, f"Invoice {inv['number']} is issued, so it cannot change. Void it and make a new one if it is wrong.",
                      code="not_draft")


async def _deal_ok(conn, deal_id, account_id) -> None:
    if deal_id:
        cur = await conn.execute("SELECT 1 FROM deals WHERE id = %s AND account_id = %s", (deal_id, account_id))
        if not await cur.fetchone():
            raise Problem(422, "That deal belongs to another client.", code="validation", fields={"deal_id": ["other client"]})


def _licence_ok(plan, starts, ends) -> None:
    if plan and (not starts or not ends):
        raise Problem(422, "Give the licence's start and end dates.", code="validation", fields={"licence_ends": ["missing"]})
    if plan and ends < starts:
        raise Problem(422, "The licence cannot end before it starts.", code="validation", fields={"licence_ends": ["before start"]})


async def _write_lines(conn, invoice_id, lines: list[dict], vat_rate) -> None:
    t = invoicing.totals(lines, vat_rate)
    await conn.execute("DELETE FROM invoice_lines WHERE invoice_id = %s", (invoice_id,))
    for i, (l, amount) in enumerate(zip(lines, t["amounts"])):
        await conn.execute("INSERT INTO invoice_lines (invoice_id, position, description, quantity, unit_price_ngn, amount_ngn) "
                           "VALUES (%s, %s, %s, %s, %s, %s)",
                           (invoice_id, i, l["description"].strip(), l["quantity"], l["unit_price_ngn"], amount))
    await conn.execute("UPDATE invoices SET subtotal_ngn = %s, vat_ngn = %s, total_ngn = %s, updated_at = now() WHERE id = %s",
                       (t["subtotal_ngn"], t["vat_ngn"], t["total_ngn"], invoice_id))


# ---------- what GeoEstate prints, and the price list ----------
@router.get("/company", response_model=CompanyOut, summary="GeoEstate's details as printed on invoices")
async def company(user=Depends(current_user)):
    s = settings
    return {"name": s.company_name, "address": s.company_address, "rc": s.company_rc, "tin": s.company_tin,
            "email": s.company_email, "phone": s.company_phone, "bank_name": s.bank_name,
            "bank_account_name": s.bank_account_name, "bank_account_number": s.bank_account_number,
            "vat_rate": s.vat_rate, "due_days": s.invoice_due_days}


@router.get("/prices", response_model=list[PriceOut], summary="What a year of each plan costs, before VAT")
async def prices(user=Depends(current_user), conn=Depends(get_conn)):
    cur = await conn.execute("SELECT p.*, u.name AS updated_by_name FROM prices p LEFT JOIN users u ON u.id = p.updated_by "
                             "ORDER BY p.amount_ngn")
    return await cur.fetchall()


@router.put("/prices/{plan}", response_model=PriceOut, summary="Change a plan's yearly price (super admins)")
async def set_price(plan: str, body: PriceIn, user=Depends(require("prices.edit")), conn=Depends(get_conn)):
    cur = await conn.execute("SELECT amount_ngn FROM prices WHERE plan = %s", (plan,))
    old = await cur.fetchone()
    if not old:
        raise Problem(404, "No such plan.", code="not_found")
    await conn.execute("UPDATE prices SET amount_ngn = %s, updated_by = %s, updated_at = now() WHERE plan = %s",
                       (body.amount_ngn, user["id"], plan))
    await audit(conn, "price.update", actor_id=user["id"], target_type="price", target_id=plan,
                plan=plan, before=str(old["amount_ngn"]), after=str(body.amount_ngn))
    cur = await conn.execute("SELECT p.*, u.name AS updated_by_name FROM prices p LEFT JOIN users u ON u.id = p.updated_by "
                             "WHERE p.plan = %s", (plan,))
    return await cur.fetchone()


# ---------- invoices ----------
@router.get("/invoices", response_model=list[InvoiceOut], summary="Invoices, newest first")
async def list_invoices(status: str | None = Query(None, pattern="^(draft|issued|paid|void|overdue|unpaid)$"),
                        account_id: UUID | None = None, q: str | None = None, limit: int = Query(300, ge=1, le=1000),
                        user=Depends(current_user), conn=Depends(get_conn)):
    where, params = ["true"], []
    if status == "overdue":
        where.append("i.status = 'issued' AND i.due_date < current_date")
    elif status == "unpaid":
        where.append("i.status = 'issued'")
    elif status:
        where.append("i.status = %s"); params.append(status)
    if account_id:
        where.append("i.account_id = %s"); params.append(account_id)
    if q:
        where.append("(i.number ILIKE %s OR a.name ILIKE %s)"); params += [f"%{q.strip()}%"] * 2
    cur = await conn.execute(INVOICE_SQL + f"WHERE {' AND '.join(where)} "
                             "ORDER BY (i.status = 'draft') DESC, i.issue_date DESC NULLS LAST, i.number DESC NULLS LAST, i.created_at DESC "
                             "LIMIT %s", (*params, limit))
    return [_shape(r) for r in await cur.fetchall()]


@router.post("/invoices", response_model=InvoiceDetail, status_code=201, summary="Start an invoice (a draft)")
async def create_invoice(body: InvoiceIn, user=Depends(require("invoices.edit")), conn=Depends(get_conn)):
    cur = await conn.execute("SELECT 1 FROM accounts WHERE id = %s", (body.account_id,))
    if not await cur.fetchone():
        raise Problem(422, "Choose a client.", code="validation", fields={"account_id": ["not found"]})
    await _deal_ok(conn, body.deal_id, body.account_id)
    _licence_ok(body.licence_plan, body.licence_starts, body.licence_ends)
    cur = await conn.execute(
        "INSERT INTO invoices (account_id, deal_id, vat_rate, notes, licence_plan, licence_starts, licence_ends, created_by) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (body.account_id, body.deal_id, settings.vat_rate, body.notes.strip(), body.licence_plan,
         body.licence_starts if body.licence_plan else None, body.licence_ends if body.licence_plan else None, user["id"]))
    iid = (await cur.fetchone())["id"]
    await _write_lines(conn, iid, [l.model_dump() for l in body.lines], settings.vat_rate)
    await audit(conn, "invoice.create", actor_id=user["id"], target_type="invoice", target_id=iid, account_id=str(body.account_id))
    return await _detail(conn, iid)


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetail)
async def get_invoice(invoice_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    return await _detail(conn, invoice_id)


@router.patch("/invoices/{invoice_id}", response_model=InvoiceDetail, summary="Change a draft")
async def update_invoice(invoice_id: UUID, body: InvoicePatch, user=Depends(require("invoices.edit")), conn=Depends(get_conn)):
    inv = await _get(conn, invoice_id, lock=True)
    _draft_only(inv)
    data = body.model_dump(exclude_unset=True)
    if "deal_id" in data:
        await _deal_ok(conn, body.deal_id, inv["account_id"])
        await conn.execute("UPDATE invoices SET deal_id = %s WHERE id = %s", (body.deal_id, invoice_id))
    if "notes" in data and body.notes is not None:
        await conn.execute("UPDATE invoices SET notes = %s WHERE id = %s", (body.notes.strip(), invoice_id))
    if body.clear_licence:
        await conn.execute("UPDATE invoices SET licence_plan = NULL, licence_starts = NULL, licence_ends = NULL WHERE id = %s",
                           (invoice_id,))
    elif {"licence_plan", "licence_starts", "licence_ends"} & set(data):
        plan = data.get("licence_plan", inv["licence_plan"])
        starts, ends = data.get("licence_starts", inv["licence_starts"]), data.get("licence_ends", inv["licence_ends"])
        _licence_ok(plan, starts, ends)
        await conn.execute("UPDATE invoices SET licence_plan = %s, licence_starts = %s, licence_ends = %s WHERE id = %s",
                           (plan, starts, ends, invoice_id))
    if body.lines is not None:
        await _write_lines(conn, invoice_id, [l.model_dump() for l in body.lines], inv["vat_rate"])
    await conn.execute("UPDATE invoices SET updated_at = now() WHERE id = %s", (invoice_id,))
    return await _detail(conn, invoice_id)


@router.delete("/invoices/{invoice_id}", status_code=204, summary="Delete a draft")
async def delete_invoice(invoice_id: UUID, user=Depends(require("invoices.edit")), conn=Depends(get_conn)):
    inv = await _get(conn, invoice_id, lock=True)
    if inv["status"] != "draft":
        raise Problem(409, "Only drafts can be deleted. An issued invoice keeps its number: void it instead.", code="not_draft")
    await conn.execute("DELETE FROM invoices WHERE id = %s", (invoice_id,))
    await audit(conn, "invoice.delete", actor_id=user["id"], target_type="invoice", target_id=invoice_id)
    return Response(status_code=204)


@router.post("/invoices/{invoice_id}/issue", response_model=InvoiceDetail, summary="Issue a draft: give it its number")
async def issue(invoice_id: UUID, body: IssueIn, user=Depends(require("invoices.edit")), conn=Depends(get_conn)):
    inv = await _get(conn, invoice_id, lock=True)
    _draft_only(inv)
    if inv["total_ngn"] <= 0:
        raise Problem(422, "The invoice comes to nothing. Add a line with a price.", code="validation", fields={"lines": ["zero"]})
    on = body.issue_date or date.today()
    due = body.due_date or on + timedelta(days=settings.invoice_due_days)
    if due < on:
        raise Problem(422, "It cannot be due before it is issued.", code="validation", fields={"due_date": ["before issue"]})
    number = await invoicing.next_number(conn, on.year)
    await conn.execute(
        "UPDATE invoices SET number = %s, status = 'issued', issue_date = %s, due_date = %s, bill_to = %s, issued_at = now(), "
        "issued_by = %s, updated_at = now() WHERE id = %s",
        (number, on, due, invoicing.jsonb(await invoicing.bill_to(conn, inv["account_id"])), user["id"], invoice_id))
    await audit(conn, "invoice.issue", actor_id=user["id"], target_type="invoice", target_id=invoice_id, number=number,
                account=inv["account_name"], total=str(inv["total_ngn"]))
    return await _detail(conn, invoice_id)


@router.get("/invoices/{invoice_id}/pdf", summary="The invoice as a PDF", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}})
async def invoice_pdf(invoice_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    inv = await _detail(conn, invoice_id)
    name = f"{inv['number'] or 'draft-invoice'}.pdf"
    return Response(pdf.render(inv), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}"', "Cache-Control": "no-store"})


@router.post("/invoices/{invoice_id}/email", response_model=InvoiceDetail, summary="Email the invoice PDF to the client")
async def email_invoice(invoice_id: UUID, body: EmailInvoiceIn, user=Depends(require("invoices.edit")), conn=Depends(get_conn)):
    inv = await _detail(conn, invoice_id)
    if inv["status"] in ("draft", "void"):
        raise Problem(409, "Issue the invoice before emailing it." if inv["status"] == "draft" else "This invoice is void.",
                      code="not_issued")
    to = (body.to or inv["bill_to"].get("email") or "").strip().lower()
    if not to:
        raise Problem(422, "This client has no email. Add one to its main contact, or type the address.", code="validation",
                      fields={"to": ["missing"]})
    who = (inv["bill_to"].get("contact") or "").split(",")[0].split(" ")[0] or "there"
    paid = inv["status"] == "paid"
    text = (f"Hello {who},\n\n"
            + (f"Thank you: invoice {inv['number']} is paid in full. A copy marked paid is attached for your records."
               if paid else
               f"Please find attached invoice {inv['number']} from {settings.company_name}, for "
               f"{pdf.ngn(inv['total_ngn'])} (VAT included), due on {invoicing.long_date(inv['due_date'])}.\n\n"
               f"Pay by bank transfer to {settings.bank_name}, account {settings.bank_account_number} "
               f"({settings.bank_account_name}), with {inv['number']} as the reference, and send us the transfer receipt.")
            + (f"\n\n{body.message.strip()}" if body.message.strip() else "")
            + f"\n\nThank you,\n{user['name']}\n{settings.company_name}")
    subject = f"{'Paid: ' if paid else ''}Invoice {inv['number']} from {settings.company_name}"
    sent = await send_email(to, subject, text, attachments=[(f"{inv['number']}.pdf", pdf.render(inv))])
    if not sent:
        raise Problem(502, "The email could not be sent. Check BREVO_API_KEY and MAIL_FROM in the CRM's variables, or "
                           "download the PDF and send it yourself.", code="email_failed")
    await conn.execute("UPDATE invoices SET emailed_at = now(), emailed_to = %s WHERE id = %s", (to, invoice_id))
    await audit(conn, "invoice.email", actor_id=user["id"], target_type="invoice", target_id=invoice_id, number=inv["number"], to=to)
    return await _detail(conn, invoice_id)


@router.post("/invoices/{invoice_id}/void", response_model=InvoiceDetail, summary="Cancel an issued invoice (it keeps its number)")
async def void(invoice_id: UUID, body: VoidIn, user=Depends(require("payments.record")), conn=Depends(get_conn)):
    inv = await _get(conn, invoice_id, lock=True)
    if inv["status"] != "issued":
        raise Problem(409, {"draft": "A draft has no number yet: delete it instead.", "void": "It is already void.",
                            "paid": "A paid invoice cannot be voided. Remove its payments first."}[inv["status"]], code="not_issued")
    if inv["paid_ngn"]:
        raise Problem(409, "This invoice has payments. Remove them first.", code="has_payments")
    await conn.execute("UPDATE invoices SET status = 'void', voided_at = now(), void_reason = %s, updated_at = now() WHERE id = %s",
                       (body.reason.strip(), invoice_id))
    await audit(conn, "invoice.void", actor_id=user["id"], target_type="invoice", target_id=invoice_id, number=inv["number"],
                reason=body.reason.strip())
    return await _detail(conn, invoice_id)


# ---------- payments ----------
@router.post("/invoices/{invoice_id}/payments", response_model=InvoiceDetail, status_code=201,
             summary="Record money received; paying in full switches on the Geohub licence")
async def add_payment(invoice_id: UUID, body: PaymentIn, user=Depends(require("payments.record")), conn=Depends(get_conn)):
    inv = await _get(conn, invoice_id, lock=True)
    if inv["status"] != "issued":
        raise Problem(409, {"draft": "Issue the invoice first.", "void": "This invoice is void.",
                            "paid": "This invoice is already paid in full."}[inv["status"]], code="not_issued")
    if body.amount_ngn > inv["balance_ngn"]:
        raise Problem(422, f"That is more than the {pdf.ngn(inv['balance_ngn'])} still owed.", code="validation",
                      fields={"amount_ngn": ["more than owed"]})
    if body.paid_on > date.today():
        raise Problem(422, "The payment date cannot be in the future.", code="validation", fields={"paid_on": ["future"]})
    cur = await conn.execute("INSERT INTO payments (invoice_id, amount_ngn, paid_on, method, reference, note, recorded_by) "
                             "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                             (invoice_id, body.amount_ngn, body.paid_on, body.method, body.reference.strip(), body.note.strip(), user["id"]))
    pid = (await cur.fetchone())["id"]
    full = body.amount_ngn == inv["balance_ngn"]
    await audit(conn, "payment.record", actor_id=user["id"], target_type="invoice", target_id=invoice_id, number=inv["number"],
                amount=str(body.amount_ngn), reference=body.reference.strip(), payment_id=str(pid), full=full)
    if full:
        await conn.execute("UPDATE invoices SET status = 'paid', paid_at = now(), updated_at = now() WHERE id = %s", (invoice_id,))
        await conn.execute("UPDATE accounts SET status = 'customer', updated_at = now() WHERE id = %s", (inv["account_id"],))
        if inv["deal_id"]:
            await conn.execute("UPDATE deals SET stage = 'won', closed_at = COALESCE(closed_at, now()), updated_at = now() "
                               "WHERE id = %s AND stage <> 'won'", (inv["deal_id"],))
        await invoicing.apply_licence(conn, await _get(conn, invoice_id), user["name"], body.lift_suspension)
    return await _detail(conn, invoice_id)


@router.delete("/payments/{payment_id}", response_model=InvoiceDetail, summary="Remove a payment recorded by mistake")
async def delete_payment(payment_id: UUID, user=Depends(require("payments.record")), conn=Depends(get_conn)):
    cur = await conn.execute("SELECT * FROM payments WHERE id = %s", (payment_id,))
    p = await cur.fetchone()
    if not p:
        raise Problem(404, "Payment not found.", code="not_found")
    inv = await _get(conn, p["invoice_id"], lock=True)
    await conn.execute("DELETE FROM payments WHERE id = %s", (payment_id,))
    if inv["status"] == "paid":
        await conn.execute("UPDATE invoices SET status = 'issued', paid_at = NULL, updated_at = now() WHERE id = %s", (inv["id"],))
    await audit(conn, "payment.delete", actor_id=user["id"], target_type="invoice", target_id=inv["id"], number=inv["number"],
                amount=str(p["amount_ngn"]), licence_was_applied=bool(inv["licence_applied_at"]))
    return await _detail(conn, inv["id"])


@router.post("/invoices/{invoice_id}/licence", response_model=InvoiceDetail,
             summary="Try again to switch on a paid invoice's Geohub licence")
async def retry_licence(invoice_id: UUID, lift_suspension: bool = False, user=Depends(require("payments.record")),
                        conn=Depends(get_conn)):
    inv = await _get(conn, invoice_id, lock=True)
    if inv["status"] != "paid" or not inv["licence_plan"]:
        raise Problem(409, "Only a paid invoice with a licence can switch one on.", code="not_paid")
    if inv["licence_applied_at"]:
        return await _detail(conn, invoice_id)
    await invoicing.apply_licence(conn, inv, user["name"], lift_suspension)
    await audit(conn, "invoice.licence", actor_id=user["id"], target_type="invoice", target_id=invoice_id, number=inv["number"])
    return await _detail(conn, invoice_id)


@router.get("/payments/recent", response_model=list[PaymentOut], summary="Latest payments received")
async def recent_payments(limit: int = Query(50, ge=1, le=500), user=Depends(current_user), conn=Depends(get_conn)):
    cur = await conn.execute("SELECT p.*, u.name AS recorded_by_name FROM payments p LEFT JOIN users u ON u.id = p.recorded_by "
                             "ORDER BY p.paid_on DESC, p.created_at DESC LIMIT %s", (limit,))
    return await cur.fetchall()
