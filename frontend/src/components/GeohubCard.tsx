import { useEffect, useState, type FormEvent } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { PRODUCT_NAME, day, planName } from "../lib/format";
import type { AccountDetail, GeohubOrg } from "../lib/types";
import { statusTone } from "../pages/GeohubPage";
import { Button, ErrorText, useAction } from "./ui";

/** The client on Geohub: its organization and licence today; link it, unlink it, or set it up there. */
export default function GeohubCard({ a, onChange }: { a: AccountDetail; onChange: () => void }) {
  const { can } = useAuth();
  const { busy, run } = useAction();
  const [org, setOrg] = useState<GeohubOrg | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [mode, setMode] = useState<"link" | "setup" | null>(null);
  const [choices, setChoices] = useState<GeohubOrg[] | null>(null);
  const [orgId, setOrgId] = useState("");
  const paid = a.invoices.filter((i) => i.status === "paid" && i.licence_plan && (i.licence_products?.length ? i.licence_products.includes("hub") : (i.licence_product ?? "hub") === "hub"));
  const [setup, setSetup] = useState({ kind: (paid.length ? "paid" : "demo") as "paid" | "demo", contact_id: a.contacts[0]?.id ?? "", invoice_id: paid[0]?.id ?? "" });

  useEffect(() => {
    setLoaded(false);
    void api.accountGeohub(a.id).then((g) => { setOrg(g.org); setError(g.error); setLoaded(true); }, (e) => { setError(String(e.message ?? e)); setLoaded(true); });
  }, [a.id, a.geohub_org_id]);
  useEffect(() => {
    if (mode === "link" && !choices) void api.geohubOrgs().then((x) => setChoices(x.filter((o) => !o.crm_account_id)), (e) => setError(e.message));
  }, [mode]);

  async function link(e: FormEvent) {
    e.preventDefault();
    if (await run("link", () => api.linkGeohub(a.id, orgId), "Linked to Geohub.")) { setMode(null); onChange(); }
  }
  async function doSetup(e: FormEvent) {
    e.preventDefault();
    const body = { kind: setup.kind, contact_id: setup.contact_id, ...(setup.kind === "paid" ? { invoice_id: setup.invoice_id } : {}) };
    const who = a.contacts.find((c) => c.id === setup.contact_id);
    if (await run("setup", () => api.setupGeohub(a.id, body), `${a.name} is set up on Geohub. ${who?.name ?? "The owner"} gets an email to choose a password.`)) { setMode(null); onChange(); }
  }
  const editable = can("geohub.link");

  return (
    <section className="card" id="geohub" aria-labelledby="gh-h">
      <div className="head"><h2 id="gh-h">Geohub</h2>
        {editable && a.geohub_org_id && <Button small variant="ghost" busy={busy === "unlink"} onClick={() => {
          if (window.confirm(`Unlink ${a.name} from its Geohub organization? Nothing changes on Geohub.`)) void run("unlink", () => api.unlinkGeohub(a.id), "Unlinked.").then(onChange);
        }}>Unlink</Button>}
      </div>
      {!loaded ? <p className="loading">Asking Geohub…</p> : org ? (
        <dl className="kv">
          <dt>Organization</dt><dd><a href={org.console_url} target="_blank" rel="noreferrer"><strong>{org.name}</strong></a></dd>
          <dt>Licence</dt><dd>{org.plan_name}{org.licence_kind === "demo" && " (demo)"} <span className={`badge ${statusTone(org.status)}`}>{org.status_name}</span></dd>
          {org.subscription_ends && <><dt>Ends</dt><dd>{day(org.subscription_ends)}{org.status === "grace" && org.grace_ends && <span className="late"> · read-only from {day(org.grace_ends)}</span>}</dd></>}
          {org.suspended_reason && <><dt>Suspended</dt><dd>{org.suspended_reason}</dd></>}
          {(org.products ?? []).filter((p) => p.product !== "hub").map((p) => <div key={p.product} className="kv-row"><dt>{PRODUCT_NAME[p.product]}</dt>
            <dd>{p.plan_name ?? p.plan} <span className={`badge ${statusTone(p.status)}`}>{p.status_name ?? p.status}</span>{p.subscription_ends ? <span className="muted"> until {day(p.subscription_ends)}</span> : null}</dd></div>)}
          <dt>Owner</dt><dd>{org.owner_name} <span className="muted">{org.owner_email}</span></dd>
          <dt>Last used</dt><dd>{org.last_active ? day(org.last_active) : "Not yet"}</dd>
        </dl>
      ) : (
        <>
          {error ? <p className="error">{error}</p> : <p className="muted">{a.geohub_org_id ? "" : "Not on Geohub yet."}</p>}
          {editable && !a.geohub_org_id && !mode && <div className="actions">
            <Button small onClick={() => setMode("link")}>Link to an organization on Geohub</Button>
            <Button small variant="primary" onClick={() => setMode("setup")}>Set up on Geohub</Button>
          </div>}
        </>
      )}
      {mode === "link" && (
        <form className="row" onSubmit={link} style={{ marginTop: 12 }}>
          <div className="field"><label htmlFor="gh-org">Organization on Geohub</label>
            <select id="gh-org" required value={orgId} onChange={(e) => setOrgId(e.target.value)}>
              <option value="">{choices ? `Choose (${choices.length} not linked)` : "Loading…"}</option>
              {choices?.map((o) => <option key={o.id} value={o.id}>{o.name} · {o.owner_email}</option>)}
            </select></div>
          <div className="actions"><Button type="submit" variant="primary" busy={busy === "link"}>Link</Button><Button variant="ghost" onClick={() => setMode(null)}>Cancel</Button></div>
        </form>
      )}
      {mode === "setup" && (
        <form className="stack" onSubmit={doSetup} style={{ marginTop: 12 }} aria-label="Set up on Geohub">
          <div className="seg" role="radiogroup" aria-label="Licence">
            <label className={setup.kind === "paid" ? "is-on" : ""}><input type="radio" name="gh-kind" checked={setup.kind === "paid"} disabled={!paid.length} onChange={() => setSetup({ ...setup, kind: "paid" })} />From a paid invoice</label>
            <label className={setup.kind === "demo" ? "is-on" : ""}><input type="radio" name="gh-kind" checked={setup.kind === "demo"} onChange={() => setSetup({ ...setup, kind: "demo" })} />A month's demo (Advanced)</label>
          </div>
          {setup.kind === "paid" && (
            <div className="field"><label htmlFor="gh-inv">Paid invoice</label>
              <select id="gh-inv" required value={setup.invoice_id} onChange={(e) => setSetup({ ...setup, invoice_id: e.target.value })}>
                {paid.map((i) => <option key={i.id} value={i.id}>{i.number}: {planName("hub", i.licence_plan!)}, {day(i.licence_starts)} to {day(i.licence_ends)}</option>)}
              </select></div>
          )}
          {!paid.length && <p className="muted small">No paid invoice with a licence yet: a paid set-up comes from one.</p>}
          <div className="field"><label htmlFor="gh-owner">Owner on Geohub</label>
            <select id="gh-owner" required value={setup.contact_id} onChange={(e) => setSetup({ ...setup, contact_id: e.target.value })}>
              <option value="">Choose a contact</option>
              {a.contacts.map((c) => <option key={c.id} value={c.id} disabled={!c.email}>{c.name}{c.email ? ` · ${c.email}` : " (no email)"}</option>)}
            </select>
            <span className="muted small">They get an email from Geohub to choose a password, then add their team.</span></div>
          <ErrorText error={a.contacts.length ? null : "Add a contact with an email first."} />
          <div className="actions"><Button type="submit" variant="primary" busy={busy === "setup"} disabled={!a.contacts.length}>Set up {a.name}</Button><Button variant="ghost" onClick={() => setMode(null)}>Cancel</Button></div>
        </form>
      )}
    </section>
  );
}
