import { useEffect, useState, type FormEvent } from "react";
import { api } from "../lib/api";
import type { Session, Step } from "../lib/types";
import Qr from "./Qr";
import { Button, ErrorText } from "./ui";

/** What comes after the password: the code from the authenticator app, or, the first time, setting it up. Everyone
 *  uses two-step sign-in; nothing opens without it. */
export default function StepFlow({ step, onSession, onRestart }: { step: Step; onSession: (s: Session) => void; onRestart: () => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [setup, setSetup] = useState<{ secret: string; otpauth_url: string } | null>(null);
  const [recovery, setRecovery] = useState(false);
  const [done, setDone] = useState<Session | null>(null);

  useEffect(() => {
    if (step.next === "enroll") void api.enrollStart(step.token).then(setSetup, setError);
  }, [step]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      if (step.next === "mfa") onSession(await api.verify(step.token, code.trim()));
      else setDone(await api.enrollFinish(step.token, code.trim()));
    } catch (err) { setError(err); setCode(""); } finally { setBusy(false); }
  }

  if (done) return (
    <div className="stack">
      <h1>Save your recovery codes</h1>
      <p>Two-step sign-in is set up. If you lose your phone, each of these codes gets you in once. Keep them somewhere safe, away from the phone; they are not shown again.</p>
      <ol className="codes">{done.recovery_codes!.map((c) => <li key={c}><code>{c}</code></li>)}</ol>
      <Button variant="primary" onClick={() => onSession(done)}>I have saved them, continue</Button>
    </div>
  );

  if (step.next === "enroll") return (
    <form className="stack" onSubmit={submit}>
      <h1>Set up two-step sign-in</h1>
      <p className="muted">Everyone on the GeoEstate staff uses it. You need an authenticator app on your phone, such as Google Authenticator or Microsoft Authenticator.</p>
      {!setup && !error && <p className="loading">Preparing…</p>}
      {setup && (
        <>
          <ol className="steps">
            <li>In the app, add an account and scan this code.<Qr text={setup.otpauth_url} label="QR code for your authenticator app" />
              <span className="muted">Cannot scan? Type this key: <code className="secret">{setup.secret.replace(/(.{4})/g, "$1 ").trim()}</code></span></li>
            <li><label htmlFor="enroll-code">Enter the 6-digit code the app shows</label>
              <input id="enroll-code" className="code-input" required inputMode="numeric" autoComplete="one-time-code" maxLength={7}
                value={code} onChange={(e) => setCode(e.target.value)} placeholder="123 456" /></li>
          </ol>
          <Button type="submit" variant="primary" busy={busy}>Turn on and sign in</Button>
        </>
      )}
      <ErrorText error={error} />
      <p className="muted"><a href="#" onClick={(e) => { e.preventDefault(); onRestart(); }}>Start again</a></p>
    </form>
  );

  return (
    <form className="stack" onSubmit={submit}>
      <h1>Two-step sign-in</h1>
      <p className="muted">{recovery ? "Enter one of your recovery codes. Each works once." : "Enter the 6-digit code your authenticator app shows for GeoEstate CRM."}</p>
      <div className="field">
        <label htmlFor="mfa-code">{recovery ? "Recovery code" : "Code"}</label>
        <input id="mfa-code" className="code-input" required autoFocus autoComplete="one-time-code" inputMode={recovery ? "text" : "numeric"}
          maxLength={recovery ? 20 : 7} value={code} onChange={(e) => setCode(e.target.value)} />
      </div>
      <ErrorText error={error} />
      <Button type="submit" variant="primary" busy={busy}>Continue</Button>
      <p className="muted">
        <a href="#" onClick={(e) => { e.preventDefault(); setRecovery(!recovery); setCode(""); setError(null); }}>{recovery ? "Use the app's code" : "Lost your phone? Use a recovery code"}</a>
        {" · "}<a href="#" onClick={(e) => { e.preventDefault(); onRestart(); }}>Start again</a>
      </p>
      {recovery && <p className="muted">No recovery codes either? A super admin can reset your two-step sign-in.</p>}
    </form>
  );
}
