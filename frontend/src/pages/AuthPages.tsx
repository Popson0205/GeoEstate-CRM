import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import StepFlow from "../components/StepFlow";
import { Button, ErrorText } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { Session, Step } from "../lib/types";

function Frame({ children }: { children: ReactNode }) {
  return (
    <main className="auth">
      <div className="auth-card">
        <img src="/logo.png" alt="GeoEstate" className="auth-logo" />
        <p className="auth-name">CRM · staff only</p>
        {children}
      </div>
    </main>
  );
}

function useFinish() {
  const { adopt } = useAuth();
  const nav = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/";
  return (s: Session) => { adopt(s); nav(from, { replace: true }); };
}

export function LoginPage() {
  const finish = useFinish();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [step, setStep] = useState<Step | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { setStep(await api.login(email.trim(), password)); } catch (err) { setError(err); } finally { setBusy(false); }
  }

  if (step) return <Frame><StepFlow step={step} onSession={finish} onRestart={() => { setStep(null); setPassword(""); }} /></Frame>;
  return (
    <Frame>
      <form className="stack" onSubmit={submit}>
        <h1>Sign in</h1>
        <div className="field"><label htmlFor="email">Email</label><input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div className="field"><label htmlFor="password">Password</label><input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></div>
        <ErrorText error={error} />
        <Button type="submit" variant="primary" busy={busy}>Continue</Button>
        <p className="muted"><Link to="/forgot-password">Forgot your password?</Link></p>
      </form>
    </Frame>
  );
}

/** From a welcome or reset email: choose a password, then two-step sign-in. */
export function SetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const finish = useFinish();
  const [info, setInfo] = useState<{ email: string; name: string; purpose: "set" | "reset" } | null>(null);
  const [linkError, setLinkError] = useState<unknown>(null);
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<Step | null>(null);
  const nav = useNavigate();

  useEffect(() => {
    if (!token) { setLinkError(new Error("This page needs the link from your email.")); return; }
    void api.passwordLink(token).then(setInfo, setLinkError);
  }, [token]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (pw !== pw2) { setError(new Error("The two passwords are not the same.")); return; }
    setBusy(true); setError(null);
    try { setStep(await api.setPassword(token, pw)); } catch (err) { setError(err); } finally { setBusy(false); }
  }

  if (step) return <Frame><StepFlow step={step} onSession={finish} onRestart={() => nav("/login")} /></Frame>;
  if (linkError) return <Frame><div className="stack"><h1>This link cannot be used</h1><ErrorText error={linkError} /><p><Link to="/forgot-password">Get a new link</Link> or <Link to="/login">sign in</Link>.</p></div></Frame>;
  if (!info) return <Frame><p className="loading">Checking your link…</p></Frame>;
  return (
    <Frame>
      <form className="stack" onSubmit={submit}>
        <h1>{info.purpose === "set" ? `Welcome, ${info.name.split(" ")[0]}` : "Choose a new password"}</h1>
        <p className="muted">You sign in as <strong>{info.email}</strong>.</p>
        <div className="field"><label htmlFor="pw">Password</label>
          <input id="pw" type="password" autoComplete="new-password" required minLength={10} value={pw} onChange={(e) => setPw(e.target.value)} aria-describedby="pw-hint" />
          <span id="pw-hint" className="muted small">At least 10 characters. A short sentence is easy to remember and hard to guess.</span></div>
        <div className="field"><label htmlFor="pw2">Type it again</label><input id="pw2" type="password" autoComplete="new-password" required minLength={10} value={pw2} onChange={(e) => setPw2(e.target.value)} /></div>
        <ErrorText error={error} />
        <Button type="submit" variant="primary" busy={busy}>Save and continue</Button>
      </form>
    </Frame>
  );
}

export function ForgotPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await api.forgot(email.trim()); setSent(true); } catch (err) { setError(err); } finally { setBusy(false); }
  }
  return (
    <Frame>
      {sent ? (
        <div className="stack" role="status"><h1>Check your email</h1>
          <p>If <strong>{email}</strong> is on the staff, a link to choose a new password is on its way. It works once, within 2 hours.</p>
          <p><Link to="/login">Back to sign in</Link></p></div>
      ) : (
        <form className="stack" onSubmit={submit}>
          <h1>Forgot your password?</h1>
          <div className="field"><label htmlFor="email">Email</label><input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <ErrorText error={error} />
          <Button type="submit" variant="primary" busy={busy}>Send the link</Button>
          <p className="muted"><Link to="/login">Back to sign in</Link></p>
        </form>
      )}
    </Frame>
  );
}
