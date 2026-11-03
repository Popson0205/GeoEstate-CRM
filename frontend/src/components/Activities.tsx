import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { KIND_LABEL, due, fromLocal, when } from "../lib/format";
import type { Activity, ActivityKind, StaffBrief } from "../lib/types";
import { Button, useAction } from "./ui";

/** Tasks (with a tick box) and logged calls, meetings, emails and notes. */
export function ActivityList({ items, onChange, showClient = true }: { items: Activity[]; onChange: () => void; showClient?: boolean }) {
  const { user, can } = useAuth();
  const { busy, run } = useAction();
  if (!items.length) return <p className="muted">Nothing here.</p>;
  return (
    <ul className="acts">
      {items.map((a) => {
        const task = a.kind === "task", d = due(a.due_at);
        return (
          <li key={a.id} className={`act${a.done_at && task ? " is-done" : ""}`}>
            {task ? (
              <input type="checkbox" aria-label={`Done: ${a.subject}`} checked={!!a.done_at} disabled={busy === a.id || !can("activities.edit")}
                onChange={(e) => void run(a.id, () => api.updateActivity(a.id, { done: e.target.checked })).then(onChange)} />
            ) : <span className={`kind kind-${a.kind}`}>{KIND_LABEL[a.kind]}</span>}
            <div className="act-main">
              <strong>{a.subject}</strong>
              {a.body && <p className="act-body">{a.body}</p>}
              <span className="muted small">
                {task && !a.done_at && <span className={d.late ? "late" : undefined}>{d.text} · </span>}
                {a.owner_name && <>{task ? "For" : "By"} {a.owner_name} · </>}
                {showClient && a.account_id && <><Link to={`/clients/${a.account_id}`}>{a.account_name}</Link>{a.deal_title ? ` · ${a.deal_title}` : ""} · </>}
                {a.done_at ? (task ? `done ${when(a.done_at)}` : when(a.done_at)) : `added ${when(a.created_at)}`}
              </span>
            </div>
            {(a.created_by_name === user?.name || user?.role === "super_admin") && (
              <Button small variant="ghost" busy={busy === `del-${a.id}`} aria-label={`Delete ${a.subject}`}
                onClick={() => { if (window.confirm(`Delete "${a.subject}"?`)) void run(`del-${a.id}`, () => api.deleteActivity(a.id)).then(onChange); }}>Delete</Button>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** Add a task for someone, or log a call, meeting, email or note. */
export function AddActivity({ staff, accountId, dealId, onAdded }: { staff: StaffBrief[]; accountId?: string; dealId?: string; onAdded: () => void }) {
  const { user } = useAuth();
  const { busy, run } = useAction();
  const [kind, setKind] = useState<ActivityKind>("task");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [owner, setOwner] = useState(user?.id ?? "");
  async function submit(e: FormEvent) {
    e.preventDefault();
    const r = await run("add", () => api.createActivity({ kind, subject: subject.trim(), body: body.trim(), account_id: accountId, deal_id: dealId,
      due_at: kind === "task" ? fromLocal(dueAt) : null, owner_id: owner || undefined, done: kind !== "task" }), kind === "task" ? "Task added." : "Logged.");
    if (r) { setSubject(""); setBody(""); setDueAt(""); onAdded(); }
  }
  return (
    <form className="add-act" onSubmit={submit}>
      <div className="seg" role="radiogroup" aria-label="What to add">
        {(Object.keys(KIND_LABEL) as ActivityKind[]).map((k) => (
          <label key={k} className={kind === k ? "is-on" : undefined}><input type="radio" name="act-kind" checked={kind === k} onChange={() => setKind(k)} />{KIND_LABEL[k]}</label>
        ))}
      </div>
      <div className="field"><label htmlFor="act-subject">{kind === "task" ? "What needs doing" : "Subject"}</label>
        <input id="act-subject" required maxLength={300} value={subject} onChange={(e) => setSubject(e.target.value)} /></div>
      <div className="field"><label htmlFor="act-body">Details <span className="muted">(optional)</span></label>
        <textarea id="act-body" rows={2} maxLength={8000} value={body} onChange={(e) => setBody(e.target.value)} /></div>
      <div className="row">
        {kind === "task" && <div className="field"><label htmlFor="act-due">Due</label><input id="act-due" type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} /></div>}
        <div className="field"><label htmlFor="act-owner">{kind === "task" ? "For" : "By"}</label>
          <select id="act-owner" value={owner} onChange={(e) => setOwner(e.target.value)}>
            {staff.map((s) => <option key={s.id} value={s.id}>{s.id === user?.id ? `${s.name} (you)` : s.name}</option>)}
          </select></div>
        <Button type="submit" variant="primary" busy={busy === "add"}>{kind === "task" ? "Add task" : `Log ${KIND_LABEL[kind].toLowerCase()}`}</Button>
      </div>
    </form>
  );
}
