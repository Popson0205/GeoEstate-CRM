import { useEffect, useState } from "react";
import { Button, ErrorText } from "../components/ui";
import { api } from "../lib/api";
import { when } from "../lib/format";
import type { AuditEntry } from "../lib/types";

const WORDS: Record<string, string> = {
  "account.create": "added a client", "account.update": "changed a client", "account.delete": "deleted a client",
  "contact.create": "added a contact", "contact.update": "changed a contact", "contact.delete": "removed a contact",
  "deal.create": "added a deal", "deal.update": "changed a deal", "deal.move": "moved a deal", "deal.delete": "deleted a deal",
  "activity.create": "added an activity", "activity.update": "changed an activity", "activity.done": "finished a task",
  "activity.reopen": "reopened a task", "activity.delete": "deleted an activity",
  "staff.add": "added a staff member", "staff.update": "changed a staff member", "staff.send_link": "sent a set-password link",
  "staff.reset_mfa": "reset someone's two-step sign-in", "auth.password_set": "chose a password", "auth.password_change": "changed their password",
  "auth.mfa_enrolled": "set up two-step sign-in", "auth.mfa_failed": "entered a wrong two-step code", "auth.recovery_code_used": "used a recovery code",
  "auth.recovery_codes": "made new recovery codes",
};
/** An entry in plain words: "Funke Ola moved a deal: Advanced, from Proposal to Won". */
export function describe(e: AuditEntry): string {
  const d = e.details as Record<string, string>;
  const what = WORDS[e.action] ?? e.action.replace(/[._]/g, " ");
  const name = d.title || d.name || d.subject || d.email;
  const move = d.from && d.to ? `, from ${d.from} to ${d.to}` : "";
  return `${what}${name ? `: ${name}` : ""}${move}`;
}

export default function LogPage() {
  const [items, setItems] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [more, setMore] = useState(false);
  useEffect(() => { void api.audit().then((x) => { setItems(x); setMore(x.length >= 100); }, setError); }, []);
  async function older() {
    const next = await api.audit(items![items!.length - 1].id);
    setItems([...items!, ...next]); setMore(next.length >= 100);
  }
  return (
    <div className="page">
      <h1>Activity log</h1>
      <p className="muted">Everything staff did in the CRM, newest first.</p>
      <ErrorText error={error} />
      {items && (
        <ol className="log">
          {items.map((e) => <li key={e.id}><span className="muted">{when(e.at)}</span><span><strong>{e.actor_name ?? "Someone"}</strong> {describe(e)}</span></li>)}
        </ol>
      )}
      {more && <Button onClick={() => void older()}>Show older</Button>}
    </div>
  );
}
