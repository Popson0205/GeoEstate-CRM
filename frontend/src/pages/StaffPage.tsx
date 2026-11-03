import { useEffect, useState, type FormEvent } from "react";
import { Button, ErrorText, useAction } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { ROLE_HELP, ROLE_LABEL, day } from "../lib/format";
import type { Role, StaffMember } from "../lib/types";

export default function StaffPage() {
  const { user, can } = useAuth();
  const { busy, run } = useAction();
  const [list, setList] = useState<StaffMember[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [f, setF] = useState({ email: "", name: "", role: "account_manager" as Role });
  const manage = can("staff.manage");
  const load = () => void api.staff().then(setList, setError);
  useEffect(load, []);

  async function add(e: FormEvent) {
    e.preventDefault();
    if (await run("add", () => api.addStaff({ ...f, email: f.email.trim(), name: f.name.trim() }), `${f.name.trim()} was added and emailed a link to choose a password.`)) {
      setF({ ...f, email: "", name: "" }); load();
    }
  }

  return (
    <div className="page">
      <h1>Staff</h1>
      {manage && (
        <form className="card grid-form" onSubmit={add} aria-label="Add a staff member">
          <h2 className="wide">Add a staff member</h2>
          <p className="muted small wide">They are emailed a link to choose a password, then set up two-step sign-in with an authenticator app. Only people you add can sign in.</p>
          <div className="field"><label htmlFor="s-name">Name</label><input id="s-name" required maxLength={120} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
          <div className="field"><label htmlFor="s-email">Email</label><input id="s-email" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
          <div className="field"><label htmlFor="s-role">Role</label>
            <select id="s-role" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>
              {(Object.keys(ROLE_LABEL) as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </select><span className="muted small">{ROLE_HELP[f.role]}</span></div>
          <div className="actions"><Button type="submit" variant="primary" busy={busy === "add"}>Add</Button></div>
        </form>
      )}
      <ErrorText error={error} />
      {list && (
        <div className="table-wrap"><table className="table">
          <thead><tr><th scope="col">Name</th><th scope="col">Role</th><th scope="col">Sign-in</th><th scope="col">Last signed in</th>{manage && <th scope="col"><span className="sr-only">Actions</span></th>}</tr></thead>
          <tbody>{list.map((s) => {
            const self = s.id === user?.id;
            return (
              <tr key={s.id} className={s.active ? undefined : "is-off"}>
                <td><strong>{s.name}{self && <span className="muted"> (you)</span>}</strong><br /><span className="muted small">{s.email}</span></td>
                <td>{manage && !self && s.active ? (
                  <select aria-label={`Role of ${s.name}`} value={s.role} disabled={busy === s.id}
                    onChange={(e) => { const role = e.target.value as Role; void run(s.id, () => api.updateStaff(s.id, { role }), `${s.name} is now ${ROLE_LABEL[role]}.`).then(load); }}>
                    {(Object.keys(ROLE_LABEL) as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                  </select>) : ROLE_LABEL[s.role]}</td>
                <td>{!s.active ? <span className="badge off">Turned off</span> : !s.password_set ? <span className="badge warn">Invited</span>
                  : s.mfa_enabled ? <span className="badge ok">Two-step on</span> : <span className="badge warn">Sets up at next sign-in</span>}</td>
                <td className="muted">{s.last_sign_in_at ? day(s.last_sign_in_at) : "Never"}</td>
                {manage && <td className="actions">{!self && (s.active ? <>
                  {!s.password_set && <Button small variant="ghost" busy={busy === `l-${s.id}`} onClick={() => void run(`l-${s.id}`, () => api.sendStaffLink(s.id), `A new link was emailed to ${s.email}.`)}>Resend link</Button>}
                  {s.mfa_enabled && <Button small variant="ghost" busy={busy === `m-${s.id}`} onClick={() => { if (window.confirm(`Reset ${s.name}'s two-step sign-in? Only for a lost or new phone.`)) void run(`m-${s.id}`, () => api.resetStaffMfa(s.id), `${s.name} sets up two-step sign-in again at the next sign-in.`).then(load); }}>Reset 2-step</Button>}
                  <Button small variant="ghost" busy={busy === `o-${s.id}`} onClick={() => { if (window.confirm(`Turn off ${s.name}'s account? They are signed out and cannot sign in; their history stays.`)) void run(`o-${s.id}`, () => api.updateStaff(s.id, { active: false }), `${s.name} can no longer sign in.`).then(load); }}>Turn off</Button>
                </> : <Button small variant="ghost" busy={busy === `o-${s.id}`} onClick={() => void run(`o-${s.id}`, () => api.updateStaff(s.id, { active: true }), `${s.name} can sign in again.`).then(load)}>Turn on</Button>)}</td>}
              </tr>
            );
          })}</tbody>
        </table></div>
      )}
    </div>
  );
}
