export type Role = "super_admin" | "account_manager" | "support" | "finance";
export type Perm = "accounts.edit" | "deals.edit" | "contacts.edit" | "activities.edit" | "records.delete" | "staff.manage" | "audit.view";
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
  country: string; status: AccountStatus; owner_id: string | null; owner_name: string | null; geohub_org_id: string | null; notes: string;
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
export interface AccountDetail extends Account { contacts: Contact[]; deals: Deal[]; activities: Activity[] }
export interface Home {
  pipeline: { stage: Stage; count: number; value_ngn: string }[]; won_this_month_ngn: string;
  accounts: Record<AccountStatus, number>; my_open_tasks: number; my_overdue: number; my_tasks: Activity[]; recent: Activity[];
}
export interface AuditEntry { id: number; at: string; actor_id: string | null; actor_name: string | null; action: string;
  target_type: string | null; target_id: string | null; details: Record<string, unknown> }
