from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

Role = Literal["super_admin", "account_manager", "support", "finance"]
Stage = Literal["new", "contacted", "demo", "proposal", "won", "lost"]
Plan = Literal["standard", "advanced", "custom", "demo", "other"]
AccountStatus = Literal["lead", "customer", "former"]
ActivityKind = Literal["task", "call", "meeting", "email", "note"]


# ---------- signing in ----------
class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class UserOut(BaseModel):
    id: UUID
    email: str
    name: str
    role: Role
    role_name: str
    perms: list[str]
    mfa_enabled: bool


class SessionOut(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: UserOut


class StepOut(BaseModel):
    """After the password: enter a code (`mfa`), or set up two-step sign-in first (`enroll`)."""
    next: Literal["mfa", "enroll"]
    token: str = Field(description="Send it back with the next step, within 5 minutes (15 to set up)")


class EnrollStartOut(BaseModel):
    secret: str
    otpauth_url: str


class CodeIn(BaseModel):
    token: str = Field(min_length=20, max_length=2000)
    code: str = Field(min_length=6, max_length=20)


class EnrolledOut(SessionOut):
    recovery_codes: list[str] = Field(description="Shown this once")


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=2000)


class RefreshIn(BaseModel):
    refresh_token: str


class SetPasswordIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=10, max_length=200)


class ForgotIn(BaseModel):
    email: EmailStr


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


class LinkOut(BaseModel):
    email: str
    name: str
    purpose: Literal["set", "reset"]


class MyCodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class RecoveryCodesOut(BaseModel):
    recovery_codes: list[str]


# ---------- staff ----------
class StaffOut(BaseModel):
    id: UUID
    email: str
    name: str
    role: Role
    active: bool
    mfa_enabled: bool
    password_set: bool
    last_sign_in_at: datetime | None
    created_at: datetime


class StaffIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    role: Role


class StaffPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    role: Role | None = None
    active: bool | None = Field(None, description="false: can no longer sign in; their history stays")


class StaffBrief(BaseModel):
    id: UUID
    name: str


# ---------- clients ----------
class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    industry: str = Field("", max_length=120)
    email: str = Field("", max_length=200)
    phone: str = Field("", max_length=60)
    website: str = Field("", max_length=200)
    address: str = Field("", max_length=400)
    city: str = Field("", max_length=120)
    state: str = Field("", max_length=120)
    country: str = Field("Nigeria", max_length=120)
    status: AccountStatus = "lead"
    owner_id: UUID | None = None
    tin: str = Field("", max_length=40, description="The client's tax number, printed on its invoices")
    notes: str = Field("", max_length=8000)


class AccountPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    industry: str | None = Field(None, max_length=120)
    email: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=60)
    website: str | None = Field(None, max_length=200)
    address: str | None = Field(None, max_length=400)
    city: str | None = Field(None, max_length=120)
    state: str | None = Field(None, max_length=120)
    country: str | None = Field(None, max_length=120)
    status: AccountStatus | None = None
    owner_id: UUID | None = None
    tin: str | None = Field(None, max_length=40)
    notes: str | None = Field(None, max_length=8000)


class AccountOut(BaseModel):
    id: UUID
    name: str
    industry: str
    email: str
    phone: str
    website: str
    address: str
    city: str
    state: str
    country: str
    status: AccountStatus
    owner_id: UUID | None
    owner_name: str | None
    geohub_org_id: UUID | None
    geohub_request_id: UUID | None = None
    tin: str = ""
    notes: str
    open_deals: int = 0
    open_value_ngn: Decimal = Decimal(0)
    primary_contact: str | None = None
    created_at: datetime
    updated_at: datetime


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    title: str = Field("", max_length=120)
    email: str = Field("", max_length=200)
    phone: str = Field("", max_length=60)
    is_primary: bool = False
    notes: str = Field("", max_length=4000)


class ContactPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=160)
    title: str | None = Field(None, max_length=120)
    email: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=60)
    is_primary: bool | None = None
    notes: str | None = Field(None, max_length=4000)


class ContactOut(BaseModel):
    id: UUID
    account_id: UUID
    name: str
    title: str
    email: str
    phone: str
    is_primary: bool
    notes: str
    created_at: datetime


class DealIn(BaseModel):
    account_id: UUID
    title: str = Field(min_length=1, max_length=200)
    plan: Plan = "standard"
    amount_ngn: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2, description="Before VAT")
    stage: Stage = "new"
    owner_id: UUID | None = None
    expected_close: date | None = None
    notes: str = Field("", max_length=8000)


class DealPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    plan: Plan | None = None
    amount_ngn: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2)
    clear_amount: bool = False
    stage: Stage | None = None
    owner_id: UUID | None = None
    expected_close: date | None = None
    lost_reason: str | None = Field(None, max_length=1000, description="Needed when moving a deal to lost")
    notes: str | None = Field(None, max_length=8000)


class DealOut(BaseModel):
    id: UUID
    account_id: UUID
    account_name: str
    title: str
    plan: Plan
    amount_ngn: Decimal | None
    stage: Stage
    owner_id: UUID | None
    owner_name: str | None
    expected_close: date | None
    lost_reason: str
    notes: str
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ActivityIn(BaseModel):
    kind: ActivityKind = "task"
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field("", max_length=8000)
    due_at: datetime | None = None
    done: bool = Field(False, description="A call, meeting, email or note logged after it happened")
    owner_id: UUID | None = Field(None, description="Who it is assigned to; you, when left out")
    account_id: UUID | None = None
    deal_id: UUID | None = None


class ActivityPatch(BaseModel):
    subject: str | None = Field(None, min_length=1, max_length=300)
    body: str | None = Field(None, max_length=8000)
    due_at: datetime | None = None
    clear_due: bool = False
    done: bool | None = None
    owner_id: UUID | None = None


class ActivityOut(BaseModel):
    id: UUID
    kind: ActivityKind
    subject: str
    body: str
    due_at: datetime | None
    done_at: datetime | None
    owner_id: UUID | None
    owner_name: str | None
    account_id: UUID | None
    account_name: str | None
    deal_id: UUID | None
    deal_title: str | None
    created_by_name: str | None
    created_at: datetime


class AccountDetail(AccountOut):
    contacts: list[ContactOut]
    deals: list[DealOut]
    activities: list[ActivityOut]
    invoices: list["InvoiceOut"] = Field(default_factory=list)


class StageTotal(BaseModel):
    stage: Stage
    count: int
    value_ngn: Decimal


class HomeOut(BaseModel):
    pipeline: list[StageTotal]
    won_this_month_ngn: Decimal
    accounts: dict[str, int] = Field(description="Clients by status")
    my_open_tasks: int
    my_overdue: int
    my_tasks: list[ActivityOut] = Field(description="Your next open tasks, soonest first")
    recent: list[ActivityOut] = Field(description="Latest activity across the CRM")
    unpaid_ngn: Decimal = Field(Decimal(0), description="Owed on issued invoices")
    overdue_ngn: Decimal = Field(Decimal(0), description="Owed on invoices past their due date")
    overdue_invoices: int = 0
    received_this_month_ngn: Decimal = Decimal(0)


class AuditOut(BaseModel):
    id: int
    at: datetime
    actor_id: UUID | None
    actor_name: str | None
    action: str
    target_type: str | None
    target_id: str | None
    details: dict


# ---------- prices, invoices and payments ----------
LicencePlan = Literal["standard", "advanced", "custom"]
Product = Literal["hub", "land", "check", "farm"]
InvoiceStatus = Literal["draft", "issued", "paid", "void"]
Money = Field(ge=0, max_digits=14, decimal_places=2)


class PriceOut(BaseModel):
    product: Product = "hub"
    plan: LicencePlan
    name: str
    amount_ngn: Decimal = Field(description="A year, before VAT")
    updated_at: datetime
    updated_by_name: str | None = None


class PriceIn(BaseModel):
    amount_ngn: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class LineIn(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    quantity: Decimal = Field(Decimal(1), gt=0, max_digits=12, decimal_places=2)
    unit_price_ngn: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class LineOut(LineIn):
    id: UUID
    amount_ngn: Decimal


class InvoiceIn(BaseModel):
    account_id: UUID
    deal_id: UUID | None = None
    lines: list[LineIn] = Field(min_length=1, max_length=50)
    notes: str = Field("", max_length=4000, description="Printed on the invoice")
    licence_product: Product = Field("hub", description="The product whose licence this invoice pays for")
    licence_plan: LicencePlan | None = Field(None, description="The licence this invoice pays for, switched on when it is paid")
    licence_starts: date | None = None
    licence_ends: date | None = None


class InvoicePatch(BaseModel):
    deal_id: UUID | None = None
    lines: list[LineIn] | None = Field(None, min_length=1, max_length=50)
    notes: str | None = Field(None, max_length=4000)
    licence_product: Product | None = None
    licence_plan: LicencePlan | None = None
    licence_starts: date | None = None
    licence_ends: date | None = None
    clear_licence: bool = False


class IssueIn(BaseModel):
    issue_date: date | None = Field(None, description="Today when left out")
    due_date: date | None = Field(None, description="14 days after the issue date when left out")


class EmailInvoiceIn(BaseModel):
    to: EmailStr | None = Field(None, description="The client's main contact when left out")
    message: str = Field("", max_length=4000)


class VoidIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class PaymentIn(BaseModel):
    amount_ngn: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    paid_on: date
    method: Literal["bank_transfer", "cash", "cheque", "other"] = "bank_transfer"
    reference: str = Field("", max_length=200, description="The bank's transfer reference")
    note: str = Field("", max_length=1000)
    lift_suspension: bool = Field(False, description="If the client is suspended on Geohub, lift it with the licence")


class PaymentOut(BaseModel):
    id: UUID
    invoice_id: UUID
    amount_ngn: Decimal
    paid_on: date
    method: str
    reference: str
    note: str
    recorded_by_name: str | None
    created_at: datetime


class InvoiceOut(BaseModel):
    id: UUID
    number: str | None
    account_id: UUID
    account_name: str
    deal_id: UUID | None
    deal_title: str | None = None
    status: InvoiceStatus
    overdue: bool
    issue_date: date | None
    due_date: date | None
    vat_rate: Decimal
    subtotal_ngn: Decimal
    vat_ngn: Decimal
    total_ngn: Decimal
    paid_ngn: Decimal
    balance_ngn: Decimal
    licence_product: Product = "hub"
    licence_plan: LicencePlan | None
    licence_starts: date | None
    licence_ends: date | None
    licence_applied_at: datetime | None
    licence_error: str | None
    emailed_at: datetime | None
    emailed_to: str | None
    paid_at: datetime | None
    voided_at: datetime | None
    void_reason: str | None
    created_by_name: str | None
    created_at: datetime


class InvoiceDetail(InvoiceOut):
    lines: list[LineOut]
    payments: list[PaymentOut]
    bill_to: dict
    notes: str
    geohub_org_id: UUID | None = Field(None, description="The client's organization on Geohub, if linked")


class CompanyOut(BaseModel):
    name: str
    address: str
    rc: str
    tin: str
    email: str
    phone: str
    bank_name: str
    bank_account_name: str
    bank_account_number: str
    vat_rate: float
    due_days: int


# ---------- Geohub ----------
class GeohubOrg(BaseModel):
    id: UUID
    name: str
    plan: str
    plan_name: str
    licence_kind: str
    status: str
    status_name: str
    subscription_starts: date | None
    subscription_ends: date | None
    grace_ends: date | None
    suspended_reason: str | None
    owner_name: str | None
    owner_email: str | None
    created_at: datetime
    last_active: datetime | None
    console_url: str
    products: list[dict] = Field(default_factory=list, description="Every product it has on Geohub, Geohub first")
    crm_account_id: UUID | None = None
    crm_account_name: str | None = None


class GeohubRequest(BaseModel):
    id: UUID
    organization: str
    contact_name: str
    email: str
    phone: str | None
    plan: str
    team_size: str | None
    message: str | None
    status: str
    org_id: UUID | None
    created_at: datetime
    crm_account_id: UUID | None = None
    crm_account_name: str | None = None


class GeohubStatusOut(BaseModel):
    linked: bool = Field(description="GEOHUB_URL and GEOHUB_LINK_KEY are set")
    url: str


class AccountGeohubOut(BaseModel):
    org: GeohubOrg | None
    error: str | None = Field(None, description="Why Geohub could not be read just now")


class LinkIn(BaseModel):
    org_id: UUID


class ImportIn(BaseModel):
    org_ids: list[UUID] = Field(default_factory=list, max_length=500)
    request_ids: list[UUID] = Field(default_factory=list, max_length=500)


class ImportOut(BaseModel):
    added: int
    skipped: int = Field(description="Already in the CRM")
    accounts: list[UUID]


class SetupIn(BaseModel):
    kind: Literal["paid", "demo"] = Field(description="paid: from a paid invoice with a licence; demo: a month of Advanced")
    contact_id: UUID = Field(description="The contact who becomes the organization's owner on Geohub")
    invoice_id: UUID | None = Field(None, description="For a paid set-up: the paid invoice")

AccountDetail.model_rebuild()
