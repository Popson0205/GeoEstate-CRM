import type { Account, AccountDetail, Activity, AuditEntry, Company, Contact, Deal, GeohubOrg, GeohubRequest, Home, Invoice, InvoiceDetail, InvoiceDraft,
  LicencePlan, Price, Product, Session, StaffBrief, StaffMember, Step, User } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string, public fields?: Record<string, string>, public code?: string) { super(message); }
}

const BASE = import.meta.env.VITE_API_URL ?? "/api";
const ACCESS = "crm.access", REFRESH = "crm.refresh";
const store = {
  get: (k: string) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
  del: (k: string) => { try { localStorage.removeItem(k); } catch { /* private mode */ } },
};
export const tokens = {
  has: () => !!store.get(ACCESS),
  save(s: Session) { store.set(ACCESS, s.access_token); store.set(REFRESH, s.refresh_token); },
  clear() { store.del(ACCESS); store.del(REFRESH); },
};

let refreshing: Promise<boolean> | null = null;
async function refresh(): Promise<boolean> {
  const rt = store.get(REFRESH);
  if (!rt) return false;
  refreshing ??= (async () => {
    try {
      const r = await fetch(`${BASE}/auth/refresh`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: rt }) });
      if (!r.ok) { tokens.clear(); return false; }
      tokens.save(await r.json());
      return true;
    } catch { return false; } finally { setTimeout(() => { refreshing = null; }, 0); }
  })();
  return refreshing;
}

/** A file from the API (an invoice PDF), signed in. */
export async function blob(path: string, retry = true): Promise<Blob> {
  const at = store.get(ACCESS);
  const res = await fetch(BASE + path, { headers: at ? { Authorization: `Bearer ${at}` } : {} }).catch(() => null);
  if (!res) throw new ApiError(0, "Can't reach the CRM. Check your connection.");
  if (res.status === 401 && retry && at && await refresh()) return blob(path, false);
  if (!res.ok) throw new ApiError(res.status, "The file could not be made.");
  return res.blob();
}

export async function req<T>(method: string, path: string, body?: unknown, retry = true): Promise<T> {
  const headers: Record<string, string> = {};
  const at = store.get(ACCESS);
  if (at) headers.Authorization = `Bearer ${at}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(BASE + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "Can't reach the CRM. Check your connection.");
  }
  if (res.status === 401 && retry && at && await refresh()) return req<T>(method, path, body, false);
  if (!res.ok) {
    let detail = res.statusText, code: string | undefined, fields: Record<string, string> | undefined;
    try {
      const p = await res.json();
      detail = p.detail || p.title || detail; code = p.code;
      if (p.fields) fields = Object.fromEntries(Object.entries(p.fields as Record<string, string[]>).map(([k, v]) => [k, v.join(", ")]));
    } catch { /* not JSON */ }
    if (res.status === 401 && at) { tokens.clear(); window.dispatchEvent(new Event("crm:signed-out")); }
    throw new ApiError(res.status, detail, fields, code);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const q = (params: Record<string, string | number | boolean | undefined | null>) => {
  const s = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => [k, String(v)]));
  return s.size ? `?${s}` : "";
};

export const api = {
  // signing in
  login: (email: string, password: string) => req<Step>("POST", "/auth/login", { email, password }, false),
  verify: async (token: string, code: string) => { const s = await req<Session>("POST", "/auth/mfa", { token, code }, false); tokens.save(s); return s; },
  enrollStart: (token: string) => req<{ secret: string; otpauth_url: string }>("POST", "/auth/enroll/start", { token }, false),
  enrollFinish: async (token: string, code: string) => { const s = await req<Session>("POST", "/auth/enroll/finish", { token, code }, false); tokens.save(s); return s; },
  passwordLink: (token: string) => req<{ email: string; name: string; purpose: "set" | "reset" }>("GET", `/auth/password-link/${encodeURIComponent(token)}`),
  setPassword: (token: string, password: string) => req<Step>("POST", "/auth/set-password", { token, password }, false),
  forgot: (email: string) => req<void>("POST", "/auth/forgot-password", { email }, false),
  changePassword: (current_password: string, new_password: string) => req<void>("POST", "/auth/change-password", { current_password, new_password }),
  newRecoveryCodes: (code: string) => req<{ recovery_codes: string[] }>("POST", "/auth/recovery-codes", { code }),
  async logout() {
    const rt = store.get(REFRESH);
    if (rt) await req<void>("POST", "/auth/logout", { refresh_token: rt }, false).catch(() => undefined);
    tokens.clear();
  },
  me: () => req<User>("GET", "/me"),
  home: () => req<Home>("GET", "/home"),
  // staff
  staff: () => req<StaffMember[]>("GET", "/staff"),
  staffBrief: () => req<StaffBrief[]>("GET", "/staff/brief"),
  addStaff: (b: { email: string; name: string; role: string }) => req<StaffMember>("POST", "/staff", b),
  updateStaff: (id: string, b: { name?: string; role?: string; active?: boolean }) => req<StaffMember>("PATCH", `/staff/${id}`, b),
  sendStaffLink: (id: string) => req<{ sent: boolean }>("POST", `/staff/${id}/send-link`),
  resetStaffMfa: (id: string) => req<StaffMember>("POST", `/staff/${id}/reset-mfa`),
  // clients
  accounts: (f: { q?: string; status?: string; owner_id?: string } = {}) => req<Account[]>("GET", `/accounts${q(f)}`),
  account: (id: string) => req<AccountDetail>("GET", `/accounts/${id}`),
  createAccount: (b: Partial<Account>) => req<Account>("POST", "/accounts", b),
  updateAccount: (id: string, b: Partial<Account>) => req<Account>("PATCH", `/accounts/${id}`, b),
  deleteAccount: (id: string) => req<void>("DELETE", `/accounts/${id}`),
  addContact: (accountId: string, b: Partial<Contact>) => req<Contact>("POST", `/accounts/${accountId}/contacts`, b),
  updateContact: (id: string, b: Partial<Contact>) => req<Contact>("PATCH", `/contacts/${id}`, b),
  deleteContact: (id: string) => req<void>("DELETE", `/contacts/${id}`),
  // deals
  deals: (f: { stage?: string; owner_id?: string; q?: string } = {}) => req<Deal[]>("GET", `/deals${q(f)}`),
  createDeal: (b: Partial<Deal> & { account_id: string; title: string }) => req<Deal>("POST", "/deals", b),
  updateDeal: (id: string, b: Partial<Deal> & { clear_amount?: boolean }) => req<Deal>("PATCH", `/deals/${id}`, b),
  deleteDeal: (id: string) => req<void>("DELETE", `/deals/${id}`),
  // activity
  activities: (f: { mine?: boolean; owner_id?: string; status?: string; due?: string; kind?: string; account_id?: string } = {}) => req<Activity[]>("GET", `/activities${q(f)}`),
  createActivity: (b: Partial<Activity> & { subject: string; done?: boolean }) => req<Activity>("POST", "/activities", b),
  updateActivity: (id: string, b: { subject?: string; body?: string; due_at?: string | null; clear_due?: boolean; done?: boolean; owner_id?: string }) => req<Activity>("PATCH", `/activities/${id}`, b),
  deleteActivity: (id: string) => req<void>("DELETE", `/activities/${id}`),
  audit: (before?: number) => req<AuditEntry[]>("GET", `/audit${q({ before })}`),
  // invoices
  company: () => req<Company>("GET", "/company"),
  prices: () => req<Price[]>("GET", "/prices"),
  setPrice: (product: Product, plan: LicencePlan, amount_ngn: string) => req<Price>("PUT", `/prices/${product}/${plan}`, { amount_ngn }),
  deletePrice: (product: Product, plan: LicencePlan) => req<void>("DELETE", `/prices/${product}/${plan}`),
  invoices: (f: { status?: string; account_id?: string; q?: string } = {}) => req<Invoice[]>("GET", `/invoices${q(f)}`),
  invoice: (id: string) => req<InvoiceDetail>("GET", `/invoices/${id}`),
  createInvoice: (b: InvoiceDraft) => req<InvoiceDetail>("POST", "/invoices", b),
  updateInvoice: (id: string, b: Partial<InvoiceDraft> & { clear_licence?: boolean }) => req<InvoiceDetail>("PATCH", `/invoices/${id}`, b),
  deleteInvoice: (id: string) => req<void>("DELETE", `/invoices/${id}`),
  issueInvoice: (id: string, b: { issue_date?: string; due_date?: string } = {}) => req<InvoiceDetail>("POST", `/invoices/${id}/issue`, b),
  emailInvoice: (id: string, b: { to?: string; message?: string }) => req<InvoiceDetail>("POST", `/invoices/${id}/email`, b),
  voidInvoice: (id: string, reason: string) => req<InvoiceDetail>("POST", `/invoices/${id}/void`, { reason }),
  invoicePdf: (id: string) => blob(`/invoices/${id}/pdf`),
  addPayment: (id: string, b: { amount_ngn: string; paid_on: string; method: string; reference: string; note: string; lift_suspension: boolean }) =>
    req<InvoiceDetail>("POST", `/invoices/${id}/payments`, b),
  deletePayment: (id: string) => req<InvoiceDetail>("DELETE", `/payments/${id}`),
  retryLicence: (id: string, lift_suspension = false) => req<InvoiceDetail>("POST", `/invoices/${id}/licence${q({ lift_suspension })}`),
  // Geohub
  geohub: () => req<{ linked: boolean; url: string }>("GET", "/geohub"),
  geohubOrgs: (query?: string) => req<GeohubOrg[]>("GET", `/geohub/orgs${q({ q: query })}`),
  geohubRequests: (status?: string) => req<GeohubRequest[]>("GET", `/geohub/requests${q({ status })}`),
  geohubImport: (b: { org_ids?: string[]; request_ids?: string[] }) => req<{ added: number; skipped: number; accounts: string[] }>("POST", "/geohub/import", b),
  accountGeohub: (id: string) => req<{ org: GeohubOrg | null; error: string | null }>("GET", `/accounts/${id}/geohub`),
  linkGeohub: (id: string, org_id: string) => req<{ org: GeohubOrg | null }>("PUT", `/accounts/${id}/geohub`, { org_id }),
  unlinkGeohub: (id: string) => req<void>("DELETE", `/accounts/${id}/geohub`),
  setupGeohub: (id: string, b: { kind: "paid" | "demo"; contact_id: string; invoice_id?: string }) => req<{ org: GeohubOrg | null }>("POST", `/accounts/${id}/geohub/setup`, b),
};
