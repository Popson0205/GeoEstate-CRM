export type Role = "super_admin" | "account_manager" | "support" | "finance";
export type Perm = "accounts.edit" | "deals.edit" | "contacts.edit" | "activities.edit" | "records.delete" | "staff.manage" | "audit.view"
  | "invoices.edit" | "payments.record" | "prices.edit" | "geohub.link";
export type Stage = "new" | "contacted" | "demo" | "proposal" | "won" | "lost";
export type Plan = "standard" | "advanced" | "custom" | "demo" | "other";
export type AccountStatus = "lead" | "customer" | "former";
export type ActivityKind = "task" | "call" | "meeting" | "email" | "note";

export interface User { id: string; email: string; name: string; role: Role; role_name: string; perms: Perm[]; mfa_enabled: boolean }
export interface Session { access_token: string; refresh_token: string; expires_in: number; user: User; recovery_codes?: string[] }
/** After the password: enter a code, or set up two-step sign-in first. */
export interface Step { next: "mfa" | "enroll"; token: string }
export interface StaffMember { id: string; email: string; name: string; role: Role; active: boolean; mfa_enabled: boolean; password_set: boolean;
  last_sign_in_at: string | null; created_at: string }
export interface StaffBrief { id: string; name: string }
export interface Account {
  id: string; name: string; industry: string; email: string; phone: string; website: string; address: string; city: string; state: string;
  country: string; status: AccountStatus; owner_id: string | null; owner_name: string | null; geohub_org_id: string | null; geohub_request_id?: string | null; tin: string; notes: string;
  open_deals: number; open_value_ngn: string; primary_contact: string | null; created_at: string; updated_at: string;
}
export interface Contact { id: string; account_id: string; name: string; title: string; email: string; phone: string; is_primary: boolean; notes: string; created_at: string }
export interface Deal {
  id: string; account_id: string; account_name: string; title: string; plan: Plan; amount_ngn: string | null; stage: Stage;
  owner_id: string | null; owner_name: string | null; expected_close: string | null; lost_reason: string; notes: string;
  closed_at: string | null; created_at: string; updated_at: string;
}
export interface Activity {
  id: string; kind: ActivityKind; subject: string; body: string; due_at: string | null; done_at: string | null;
  owner_id: string | null; owner_name: string | null; account_id: string | null; account_name: string | null;
  deal_id: string | null; deal_title: string | null; created_by_name: string | null; created_at: string;
}
export interface AccountDetail extends Account { contacts: Contact[]; deals: Deal[]; activities: Activity[]; invoices: Invoice[] }
export interface Home {
  pipeline: { stage: Stage; count: number; value_ngn: string }[]; won_this_month_ngn: string;
  accounts: Record<AccountStatus, number>; my_open_tasks: number; my_overdue: number; my_tasks: Activity[]; recent: Activity[];
  unpaid_ngn: string; overdue_ngn: string; overdue_invoices: number; received_this_month_ngn: string;
}
export interface AuditEntry { id: number; at: string; actor_id: string | null; actor_name: string | null; action: string;
  target_type: string | null; target_id: string | null; details: Record<string, unknown> }

export type LicencePlan = "standard" | "advanced" | "custom";
export type Product = "hub" | "land" | "check" | "farm" | "gis";
export type InvoiceStatus = "draft" | "issued" | "paid" | "void";
export interface Price { product: Product; plan: LicencePlan; name: string; amount_ngn: string; updated_at: string; updated_by_name: string | null }
export interface Company { name: string; address: string; rc: string; tin: string; email: string; phone: string; bank_name: string;
  bank_account_name: string; bank_account_number: string; vat_rate: number; due_days: number }
/** A line of an invoice. A line can pay for one product's licence (one line per product); one without is a service, e.g. training. */
export interface Line { id?: string; description: string; quantity: string; unit_price_ngn: string; amount_ngn?: string;
  licence_product?: Product | null; licence_plan?: LicencePlan | null; licence_starts?: string | null; licence_ends?: string | null;
  licence_applied_at?: string | null; licence_error?: string | null }
export interface Payment { id: string; invoice_id: string; amount_ngn: string; paid_on: string; method: string; reference: string; note: string;
  recorded_by_name: string | null; created_at: string }
export interface Invoice {
  id: string; number: string | null; account_id: string; account_name: string; deal_id: string | null; deal_title: string | null;
  status: InvoiceStatus; overdue: boolean; issue_date: string | null; due_date: string | null; vat_rate: string;
  subtotal_ngn: string; vat_ngn: string; total_ngn: string; paid_ngn: string; balance_ngn: string;
  licence_product: Product; licence_products?: Product[]; licence_plan: LicencePlan | null; licence_starts: string | null; licence_ends: string | null; licence_applied_at: string | null;
  licence_error: string | null; emailed_at: string | null; emailed_to: string | null; paid_at: string | null; voided_at: string | null;
  void_reason: string | null; created_by_name: string | null; created_at: string;
}
export interface BillTo { name: string; address: string[]; email: string; phone: string; tin: string; contact: string | null }
export interface InvoiceDetail extends Invoice { lines: Line[]; payments: Payment[]; bill_to: BillTo; notes: string; geohub_org_id: string | null; terms?: string | null }
/** The terms and conditions printed on invoices. */
export interface Terms { body: string; updated_at: string; updated_by_name: string | null }
export interface InvoiceDraft { account_id: string; deal_id?: string | null; lines: Line[]; notes: string }
export interface GeohubOrg {
  id: string; name: string; plan: string; plan_name: string; licence_kind: "paid" | "demo"; status: string; status_name: string;
  subscription_starts: string | null; subscription_ends: string | null; grace_ends: string | null; suspended_reason: string | null;
  owner_name: string | null; owner_email: string | null; created_at: string; last_active: string | null; console_url: string;
  products?: { product: Product; plan: string; plan_name?: string; status: string; status_name?: string; subscription_ends?: string | null; licence_kind?: string }[];
  crm_account_id: string | null; crm_account_name: string | null;
}
export interface GeohubRequest {
  id: string; organization: string; contact_name: string; email: string; phone: string | null; plan: string; team_size: string | null;
  message: string | null; status: string; org_id: string | null; created_at: string; crm_account_id: string | null; crm_account_name: string | null;
}
