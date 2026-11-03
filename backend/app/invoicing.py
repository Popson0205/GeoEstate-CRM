"""Invoice arithmetic, numbering, and the licence a paid invoice switches on in Geohub.

Money is Decimal throughout, rounded half-up to the kobo. VAT is on the subtotal, at the invoice's own rate (7.5% when
it was made). Numbers run GE-<year>-0001 with no gaps: a draft has none, and one is given only when it is issued."""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from psycopg.types.json import Jsonb

from . import geohub
from .config import settings

KOBO = Decimal("0.01")
PLAN_NAMES = {"standard": "Organization Standard", "advanced": "Organization Advanced"}


def money(x) -> Decimal:
    return Decimal(x).quantize(KOBO, rounding=ROUND_HALF_UP)


def totals(lines: list[dict], vat_rate) -> dict:
    amounts = [money(Decimal(l["quantity"]) * Decimal(l["unit_price_ngn"])) for l in lines]
    subtotal = money(sum(amounts, Decimal(0)))
    vat = money(subtotal * Decimal(str(vat_rate)) / 100)
    return {"amounts": amounts, "subtotal_ngn": subtotal, "vat_ngn": vat, "total_ngn": subtotal + vat}


async def next_number(conn, year: int) -> str:
    cur = await conn.execute("INSERT INTO invoice_counters (year, last) VALUES (%s, 1) "
                             "ON CONFLICT (year) DO UPDATE SET last = invoice_counters.last + 1 RETURNING last", (year,))
    n = (await cur.fetchone())["last"]
    return f"{settings.invoice_prefix}-{year}-{n:04d}"


def licence_dates(current_end: date | None, today: date | None = None) -> tuple[date, date]:
    """A year's licence: from the day after the current one ends (a renewal), or from today."""
    today = today or date.today()
    start = current_end + timedelta(days=1) if current_end and current_end >= today else today
    try:
        end = start.replace(year=start.year + 1) - timedelta(days=1)
    except ValueError:                                   # 29 February
        end = start + timedelta(days=364)
    return start, end


def licence_line(plan: str, starts: date, ends: date) -> str:
    return f"Geohub {PLAN_NAMES[plan]} licence, one year ({long_date(starts)} to {long_date(ends)})"


def long_date(d: date | None) -> str:
    return f"{d.day} {d:%B %Y}" if d else ""


async def bill_to(conn, account_id) -> dict:
    """The client as it stands now, kept on the invoice when it is issued."""
    cur = await conn.execute("SELECT name, address, city, state, country, email, phone, tin FROM accounts WHERE id = %s", (account_id,))
    a = await cur.fetchone()
    cur = await conn.execute("SELECT name, title, email, phone FROM contacts WHERE account_id = %s "
                             "ORDER BY is_primary DESC, created_at LIMIT 1", (account_id,))
    c = await cur.fetchone()
    place = ", ".join(x for x in (a["city"], a["state"]) if x)
    return {"name": a["name"], "address": [x for x in (a["address"], place, a["country"]) if x],
            "email": (c and c["email"]) or a["email"], "phone": (c and c["phone"]) or a["phone"], "tin": a["tin"],
            "contact": c and (c["name"] + (f", {c['title']}" if c["title"] else ""))}


async def apply_licence(conn, inv: dict, staff_name: str, lift_suspension: bool = False) -> None:
    """Switch on the licence a paid invoice buys, and note how it went on the invoice. Never raises: the payment is
    kept either way, and staff can try again from the invoice."""
    if not inv["licence_plan"] or inv["licence_applied_at"]:
        return
    cur = await conn.execute("SELECT geohub_org_id FROM accounts WHERE id = %s", (inv["account_id"],))
    org_id = (await cur.fetchone())["geohub_org_id"]
    error = None
    if not org_id:
        error = ("This client is not linked to Geohub yet. Link it to its organization (or set one up) on the client's "
                 "page, then switch on the licence from this invoice.")
    else:
        try:
            await geohub.call("POST", f"/orgs/{org_id}/licence", json={
                "plan": inv["licence_plan"], "subscription_starts": inv["licence_starts"].isoformat(),
                "subscription_ends": inv["licence_ends"].isoformat(), "invoice_ref": inv["number"],
                "staff_name": staff_name, "lift_suspension": lift_suspension})
        except geohub.GeohubError as e:
            error = str(e)
    if error:
        await conn.execute("UPDATE invoices SET licence_error = %s WHERE id = %s", (error, inv["id"]))
    else:
        await conn.execute("UPDATE invoices SET licence_applied_at = now(), licence_error = NULL WHERE id = %s", (inv["id"],))


# ---------- the amount in words, as Nigerian invoices print it ----------
ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
        "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
SCALES = [(10**12, "trillion"), (10**9, "billion"), (10**6, "million"), (1000, "thousand")]


def _below_1000(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    out = []
    if hundreds:
        out.append(f"{ONES[hundreds]} hundred")
    if rest:
        words = ONES[rest] if rest < 20 else TENS[rest // 10] + (f"-{ONES[rest % 10]}" if rest % 10 else "")
        out.append(("and " if hundreds else "") + words)
    return " ".join(out)


def number_words(n: int) -> str:
    if n == 0:
        return "zero"
    parts = []
    for size, name in SCALES:
        if n >= size:
            parts.append(f"{number_words(n // size)} {name}")
            n %= size
    if n:
        parts.append(("and " if parts and n < 100 else "") + _below_1000(n))
    return " ".join(parts)


def naira_words(amount) -> str:
    amount = money(amount)
    naira, kobo = int(amount), int((amount - int(amount)) * 100)
    words = f"{number_words(naira)} naira" + (f", {number_words(kobo)} kobo" if kobo else "") + " only"
    return words[0].upper() + words[1:]


def jsonb(x):
    return Jsonb(x)
