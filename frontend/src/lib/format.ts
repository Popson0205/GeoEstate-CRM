import type { AccountStatus, ActivityKind, Plan, Role, Stage } from "./types";

export const STAGES: { id: Stage; label: string }[] = [
  { id: "new", label: "New" }, { id: "contacted", label: "Contacted" }, { id: "demo", label: "Demo" },
  { id: "proposal", label: "Proposal" }, { id: "won", label: "Won" }, { id: "lost", label: "Lost" },
];
export const STAGE_LABEL = Object.fromEntries(STAGES.map((s) => [s.id, s.label])) as Record<Stage, string>;
export const PLAN_LABEL: Record<Plan, string> = { standard: "Organization Standard", advanced: "Organization Advanced", custom: "Custom", demo: "Demo licence", other: "Other" };
export const STATUS_LABEL: Record<AccountStatus, string> = { lead: "Lead", customer: "Customer", former: "Former customer" };
export const ROLE_LABEL: Record<Role, string> = { super_admin: "Super admin", account_manager: "Account manager", support: "Support", finance: "Finance" };
export const ROLE_HELP: Record<Role, string> = {
  super_admin: "Everything, including staff and deleting records",
  account_manager: "Clients, contacts, deals and activity",
  support: "Contacts and activity; sees everything else",
  finance: "Activity and the activity log; sees everything else",
};
export const KIND_LABEL: Record<ActivityKind, string> = { task: "Task", call: "Call", meeting: "Meeting", email: "Email", note: "Note" };

const NGN = new Intl.NumberFormat("en-NG", { style: "currency", currency: "NGN", maximumFractionDigits: 0 });
/** ₦1,500,000; an empty amount reads as a dash. */
export const naira = (v: string | number | null | undefined) => (v === null || v === undefined || v === "" ? "—" : NGN.format(Number(v)));

export const day = (d: string | null | undefined) =>
  d ? new Date(d.length === 10 ? `${d}T00:00:00` : d).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "";
export const when = (d: string) => new Date(d).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** How a due date reads, and whether it is late. */
export function due(d: string | null, now = Date.now()): { text: string; late: boolean } {
  if (!d) return { text: "No due date", late: false };
  const t = Date.parse(d), today = new Date(now); today.setHours(0, 0, 0, 0);
  const days = Math.floor((t - today.getTime()) / 86400000);
  if (t < now) return { text: days === 0 ? "Due today, late" : `${-days} day${days === -1 ? "" : "s"} late`, late: true };
  return { text: days === 0 ? "Due today" : days === 1 ? "Due tomorrow" : `Due ${day(d)}`, late: false };
}

/** A datetime-local input's value as an ISO time, and back. */
export const fromLocal = (v: string) => (v ? new Date(v).toISOString() : null);
export const toLocal = (iso: string | null) => {
  if (!iso) return "";
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};

/** "1 deal", "3 deals". */
export const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
