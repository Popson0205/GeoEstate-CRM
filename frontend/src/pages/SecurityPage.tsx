import { useState, type FormEvent } from "react";
import { Button, ErrorText, useAction } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";

export default function SecurityPage() {
  const { user } = useAuth();
  const { busy, run } = useAction();
  const [cur, setCur] = useState(""), [pw, setPw] = useState("");
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  async function change(e: FormEvent) {
    e.preventDefault();
    if (await run("pw", () => api.changePassword(cur, pw).then(() => true), "Password changed.")) { setCur(""); setPw(""); }
  }
  async function newCodes(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try { setCodes((await api.newRecoveryCodes(code.trim())).recovery_codes); setCode(""); } catch (err) { setError(err); }
  }
  return (
    <div className="page">
      <h1>Your account</h1>
      <p className="muted">{user?.name} · {user?.email} · {user?.role_name}</p>
      <div className="two">
        <form className="card stack" onSubmit={change}>
          <h2>Change password</h2>
          <div className="field"><label htmlFor="cur">Current password</label><input id="cur" type="password" required autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} /></div>
          <div className="field"><label htmlFor="new">New password</label><input id="new" type="password" required minLength={10} autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} /></div>
          <Button type="submit" variant="primary" busy={busy === "pw"}>Change password</Button>
        </form>
        <form className="card stack" onSubmit={newCodes}>
          <h2>Recovery codes</h2>
          <p className="muted small">Two-step sign-in is on. If you have used or lost your recovery codes, make new ones; the old ones stop working.</p>
          <div className="field"><label htmlFor="rc">Code from your app</label><input id="rc" className="code-input" required inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} /></div>
          <ErrorText error={error} />
          <Button type="submit">Make new codes</Button>
          {codes && <ol className="codes" aria-label="New recovery codes">{codes.map((c) => <li key={c}><code>{c}</code></li>)}</ol>}
        </form>
      </div>
    </div>
  );
}
