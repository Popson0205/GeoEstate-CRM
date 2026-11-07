"""The invoice as an A4 PDF: GeoEstate's logo and details, the client, the lines, VAT, the amount in words, the bank
details for the transfer, and a PAID / VOID / DRAFT mark."""
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from .config import settings
from .invoicing import licence_title, long_date, naira_words

ASSETS = Path(__file__).resolve().parent / "assets"
NAVY = colors.HexColor("#1b2b5e")
GREEN = colors.HexColor("#2f8a3b")
INK = colors.HexColor("#1a2233")
MUTED = colors.HexColor("#5c677a")
RULE = colors.HexColor("#d9dee7")
SOFT = colors.HexColor("#f2f4f8")

METHODS = {"bank_transfer": "Bank transfer", "cash": "Cash", "cheque": "Cheque", "other": "Other"}
_fonts = False


def _register() -> None:
    global _fonts
    if _fonts:
        return
    for name, file in (("Plex", "Regular"), ("Plex-Semi", "SemiBold"), ("Plex-Bold", "Bold")):
        pdfmetrics.registerFont(TTFont(name, str(ASSETS / "fonts" / f"IBMPlexSans-{file}.ttf")))
    pdfmetrics.registerFontFamily("Plex", normal="Plex", bold="Plex-Bold", italic="Plex", boldItalic="Plex-Bold")
    _fonts = True


def ngn(x, sign: bool = True) -> str:
    return ("₦" if sign else "") + f"{x:,.2f}"


def qty(x) -> str:
    return f"{x:,.2f}".rstrip("0").rstrip(".")


def render(inv: dict) -> bytes:
    _register()
    s = {
        "body": ParagraphStyle("body", fontName="Plex", fontSize=9, leading=12.5, textColor=INK),
        "muted": ParagraphStyle("muted", fontName="Plex", fontSize=8.5, leading=12, textColor=MUTED),
        "label": ParagraphStyle("label", fontName="Plex-Semi", fontSize=7.5, leading=10, textColor=MUTED, spaceAfter=2),
        "strong": ParagraphStyle("strong", fontName="Plex-Semi", fontSize=10, leading=13.5, textColor=INK),
        "title": ParagraphStyle("title", fontName="Plex-Bold", fontSize=24, leading=28, textColor=NAVY, alignment=TA_RIGHT),
        "right": ParagraphStyle("right", fontName="Plex", fontSize=9, leading=13, textColor=INK, alignment=TA_RIGHT),
        "cell": ParagraphStyle("cell", fontName="Plex", fontSize=9, leading=12, textColor=INK),
        "th": ParagraphStyle("th", fontName="Plex-Semi", fontSize=8, leading=10, textColor=colors.white),
        "thr": ParagraphStyle("thr", fontName="Plex-Semi", fontSize=8, leading=10, textColor=colors.white, alignment=TA_RIGHT),
        "cellr": ParagraphStyle("cellr", fontName="Plex", fontSize=9, leading=12, textColor=INK, alignment=TA_RIGHT),
    }
    P = lambda text, style="body": Paragraph(text, s[style])          # noqa: E731
    e = lambda x: escape(str(x or ""))                                # noqa: E731
    width = A4[0] - 36 * mm
    story = []

    # ---- header: logo and GeoEstate | INVOICE, number and dates ----
    logo = Image(str(ASSETS / "logo.png"), width=24 * mm, height=24 * mm)
    company = [P(f"<b>{e(settings.company_name)}</b>", "strong"), P(f"RC {e(settings.company_rc)} · TIN {e(settings.company_tin)}", "muted")]
    contact = " · ".join(x for x in (settings.company_email, settings.company_phone) if x)
    if contact:
        company.append(P(e(contact), "muted"))
    status = inv["status"]
    title = {"draft": "DRAFT INVOICE", "void": "INVOICE (VOID)"}.get(status, "INVOICE")
    facts = [["Invoice number", inv["number"] or "Not issued yet"], ["Date", long_date(inv["issue_date"]) or "—"],
             ["Due", long_date(inv["due_date"]) or "—"]]
    facts_t = Table([[P(k, "muted"), P(f"<b>{e(v)}</b>", "right")] for k, v in facts], colWidths=[30 * mm, 40 * mm])
    facts_t.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    left = Table([[logo, company]], colWidths=[28 * mm, 68 * mm])
    left.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    head = Table([[left, [P(title, "title"), Spacer(1, 4), facts_t]]], colWidths=[width - 72 * mm, 72 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    story += [head, Spacer(1, 8 * mm)]

    # ---- bill to | licence ----
    b = inv["bill_to"] or {}
    bill = [P("BILL TO", "label"), P(f"<b>{e(b.get('name') or inv['account_name'])}</b>", "strong")]
    bill += [P(e(x)) for x in b.get("address") or []]
    if b.get("contact"):
        bill.append(P(f"Attention: {e(b['contact'])}"))
    for x in (b.get("email"), b.get("phone")):
        if x:
            bill.append(P(e(x), "muted"))
    if b.get("tin"):
        bill.append(P(f"TIN {e(b['tin'])}", "muted"))
    right = []
    lic = [l for l in inv["lines"] if l.get("licence_plan")]
    if not lic and inv.get("licence_plan"):                    # an invoice made before licences moved onto lines
        lic = [{k: inv.get(k) for k in ("licence_product", "licence_plan", "licence_starts", "licence_ends")}]
    if lic:
        right = [P("LICENCES" if len(lic) > 1 else "LICENCE", "label")]
        for l in lic:
            right += [P(f"<b>{e(licence_title(l.get('licence_product') or 'hub', l['licence_plan']))}</b>", "strong"),
                      P(f"{e(long_date(l['licence_starts']))} to {e(long_date(l['licence_ends']))}")]
        right.append(P(("Switched on by this payment." if status == "paid" else "Switched on when this invoice is paid.")
                       if len(lic) == 1 else ("All switched on by this payment." if status == "paid" else
                                              "All switched on when this invoice is paid."), "muted"))
    meta = Table([[bill, right]], colWidths=[width * 0.58, width * 0.42])
    meta.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [meta, Spacer(1, 7 * mm)]

    # ---- the lines ----
    rows = [[P("#", "th"), P("Description", "th"), P("Qty", "thr"), P("Unit price (₦)", "thr"), P("Amount (₦)", "thr")]]
    for i, l in enumerate(inv["lines"], 1):
        rows.append([P(str(i), "cell"), P(e(l["description"]), "cell"), P(qty(l["quantity"]), "cellr"),
                     P(ngn(l["unit_price_ngn"], False), "cellr"), P(ngn(l["amount_ngn"], False), "cellr")])
    lines = Table(rows, colWidths=[8 * mm, width - 8 * mm - 16 * mm - 32 * mm - 32 * mm, 16 * mm, 32 * mm, 32 * mm], repeatRows=1)
    lines.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                               ("LINEBELOW", (0, 1), (-1, -1), 0.5, RULE),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT])]))
    story += [lines, Spacer(1, 4 * mm)]

    # ---- totals ----
    rate = f"{inv['vat_rate']:.2f}".rstrip("0").rstrip(".")
    tot = [["Subtotal", ngn(inv["subtotal_ngn"])], [f"VAT ({rate}%)", ngn(inv["vat_ngn"])], ["Total", ngn(inv["total_ngn"])]]
    if inv["paid_ngn"]:
        tot += [["Paid", f"− {ngn(inv['paid_ngn'])}"], ["Balance due", ngn(inv["balance_ngn"])]]
    tt = Table([[P(k, "right"), P(v, "right")] for k, v in tot], colWidths=[44 * mm, 40 * mm])
    style = [("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
             ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
             ("LINEABOVE", (0, 2), (-1, 2), 0.8, NAVY)]
    tt.setStyle(TableStyle(style))
    for r in (2, len(tot) - 1):
        tt._cellvalues[r] = [P(f"<b>{e(tot[r][0])}</b>", "right"), P(f"<b>{e(tot[r][1])}</b>", "right")]
    words = P(f"<b>Amount in words:</b> {e(naira_words(inv['total_ngn']))}", "body")
    row = Table([[words, tt]], colWidths=[width - 84 * mm, 84 * mm])
    row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), 10 * mm)]))
    story += [row, Spacer(1, 8 * mm)]

    # ---- money received, then how to pay what is left ----
    if inv.get("payments"):
        prow = [[P("PAYMENTS RECEIVED", "label"), "", ""]]
        for x in inv["payments"]:
            prow.append([P(e(long_date(x["paid_on"]))), P(e(x["reference"] or METHODS.get(x["method"], x["method"])), "muted"),
                         P(ngn(x["amount_ngn"]), "right")])
        ptab = Table(prow, colWidths=[40 * mm, width - 40 * mm - 40 * mm - 2, 40 * mm])
        ptab.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1, GREEN if status == "paid" else RULE), ("SPAN", (0, 0), (-1, 0)),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                  ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                                  ("TOPPADDING", (0, 0), (-1, 0), 7), ("BOTTOMPADDING", (0, -1), (-1, -1), 7)]))
        story += [KeepTogether([ptab]), Spacer(1, 5 * mm)]
    if status != "paid":
        ref = inv["number"] or "the invoice number"
        pay = [[P("HOW TO PAY: BANK TRANSFER", "label"), ""],
               [P("Bank", "muted"), P(f"<b>{e(settings.bank_name)}</b>")],
               [P("Account name", "muted"), P(f"<b>{e(settings.bank_account_name)}</b>")],
               [P("Account number", "muted"), P(f"<b>{e(settings.bank_account_number)}</b>", "strong")],
               [P("Reference", "muted"), P(f"<b>{e(ref)}</b>")]]
        pt = Table(pay, colWidths=[32 * mm, width - 32 * mm - 2])
        pt.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1, GREEN), ("SPAN", (0, 0), (1, 0)),
                                ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), ("TOPPADDING", (0, 0), (-1, 0), 7),
                                ("BOTTOMPADDING", (0, -1), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        after = P(f"Please use <b>{e(ref)}</b> as the transfer reference, and send the transfer receipt to "
                  f"{e(settings.company_email)}.", "muted")
        story.append(KeepTogether([pt, Spacer(1, 2.5 * mm), after]))
    if inv.get("notes"):
        story += [Spacer(1, 6 * mm), P("NOTES", "label"), P(e(inv["notes"]).replace("\n", "<br/>"))]

    mark = {"paid": ("PAID", GREEN), "void": ("VOID", colors.HexColor("#b3261e")), "draft": ("DRAFT", MUTED)}.get(status)

    def page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Plex", 7.5)
        canvas.setFillColor(MUTED)
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(18 * mm, 16.5 * mm, A4[0] - 18 * mm, 16.5 * mm)
        canvas.drawString(18 * mm, 12.5 * mm, " · ".join(x for x in (settings.company_name, settings.company_address) if x))
        canvas.drawString(18 * mm, 9 * mm, " · ".join(x for x in (f"RC {settings.company_rc}", f"TIN {settings.company_tin}",
                                                                 settings.company_email, settings.company_phone) if x))
        canvas.drawRightString(A4[0] - 18 * mm, 12.5 * mm, f"{inv['number'] or 'Draft'} · page {doc.page}")
        canvas.setStrokeColor(NAVY)
        canvas.setLineWidth(3)
        canvas.line(0, A4[1] - 1.5, A4[0], A4[1] - 1.5)
        canvas.restoreState()

    def stamp(canvas):
        if mark:
            canvas.saveState()
            canvas.setFont("Plex-Bold", 72)
            canvas.setFillColor(mark[1])
            canvas.setFillAlpha(0.14)
            canvas.translate(A4[0] / 2, A4[1] / 2 + 10 * mm)
            canvas.rotate(28)
            canvas.drawCentredString(0, 0, mark[0])
            canvas.restoreState()

    class Doc(SimpleDocTemplate):
        def afterPage(self):
            stamp(self.canv)

    buf = BytesIO()
    title_text = f"Invoice {inv['number']}" if inv["number"] else "Draft invoice"
    doc = Doc(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=20 * mm,
                            title=f"{title_text} · {settings.company_name}", author=settings.company_name)
    doc.build(story, onFirstPage=page, onLaterPages=page)
    return buf.getvalue()
