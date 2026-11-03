import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button, ErrorText, useAction } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { day, plural } from "../lib/format";
import type { GeohubOrg, GeohubRequest } from "../lib/types";

const ASKED: Record<string, string> = { standard: "Organization Standard", advanced: "Organization Advanced", custom: "Custom", demo: "A month's demo", unsure: "Not sure yet" };
const REQ_STATUS: Record<string, string> = { new: "New", contacted: "Contacted", set_up: "Set up", declined: "Declined" };

export function statusTone(s: string) {
  return s === "active" ? "ok" : s === "grace" || s === "demo" ? "warn" : s === "expired" || s === "suspended" ? "bad" : "";
}

/** Geohub's customers and website requests, and which are in the CRM; bring the rest in. */
export default function GeohubPage() {
  const { can } = useAuth();
  const nav = useNavigate();
  const { busy, run } = useAction();
  const [tab, setTab] = useState<"orgs" | "requests">("requests");
  const [linked, setLinked] = useState<boolean | null>(null);
  const [orgs, setOrgs] = useState<GeohubOrg[] | null>(null);
  const [reqs, setReqs] = useState<GeohubRequest[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());

  const load = () => {
    setError(null);
    void api.geohub().then((s) => {
      setLinked(s.linked);
      if (!s.linked) return;
      void api.geohubOrgs().then(setOrgs, setError);
      void api.geohubRequests().then(setReqs, setError);
    }, setError);
  };
  useEffect(load, []);
  const toggle = (id: string) => setPicked((p) => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  async function bringIn() {
    const ids = [...picked];
    const r = await run("import", () => api.geohubImport(tab === "orgs" ? { org_ids: ids } : { request_ids: ids }));
    if (!r) return;
    setPicked(new Set());
    if (r.added === 1 && r.accounts[0]) { nav(`/clients/${r.accounts[0]}`); return; }
    load();
  }

  if (linked === false) return (
    <div className="page"><h1>Geohub</h1>
      <section className="card"><p>The CRM is not linked to Geohub yet. On Railway:</p>
        <ol className="steps-list">
          <li>In <strong>Geohub's</strong> variables, set <code>CRM_LINK_KEY</code> to a long random string (32 characters or more).</li>
          <li>In the <strong>CRM's</strong> variables, set <code>GEOHUB_LINK_KEY</code> to the same string, and <code>GEOHUB_URL</code> to Geohub's address.</li>
        </ol>
        <p className="muted">Then Geohub's customers and website requests show here, and paid invoices switch licences on by themselves.</p></section>
    </div>
  );
  const rows = tab === "orgs" ? orgs : reqs;
  const free = (rows ?? []).filter((x) => !x.crm_account_id);
  return (
    <div className="page">
      <h1>Geohub</h1>
      <div className="toolbar">
        <div className="chips" role="tablist" aria-label="Show">
          <button type="button" role="tab" aria-selected={tab === "requests"} className={`chip${tab === "requests" ? " is-on" : ""}`} onClick={() => { setTab("requests"); setPicked(new Set()); }}>
            Website requests{reqs ? ` (${reqs.filter((r) => r.status === "new").length} new)` : ""}</button>
          <button type="button" role="tab" aria-selected={tab === "orgs"} className={`chip${tab === "orgs" ? " is-on" : ""}`} onClick={() => { setTab("orgs"); setPicked(new Set()); }}>
            Customers{orgs ? ` (${orgs.length})` : ""}</button>
        </div>
        {can("geohub.link") && <div className="actions">
          {free.length > 0 && <Button small variant="ghost" onClick={() => setPicked(new Set(free.map((x) => x.id)))}>Pick all {free.length} not in the CRM</Button>}
          <Button variant="primary" disabled={!picked.size} busy={busy === "import"} onClick={() => void bringIn()}>
            {picked.size ? `Add ${plural(picked.size, "client")} to the CRM` : "Add to the CRM"}</Button>
        </div>}
      </div>
      <ErrorText error={error} />
      {!rows ? (!error && <p className="loading">Asking Geohub…</p>) : rows.length === 0 ? <p className="muted">Nothing here yet.</p> : (
        <div className="table-wrap">
          <table className="table">
            {tab === "orgs" ? (
              <>
                <thead><tr><th scope="col"><span className="sr-only">Pick</span></th><th scope="col">Organization</th><th scope="col">Licence</th><th scope="col">Ends</th><th scope="col">Owner</th><th scope="col">In the CRM</th></tr></thead>
                <tbody>{(orgs ?? []).map((o) => (
                  <tr key={o.id}>
                    <td>{!o.crm_account_id && can("geohub.link") && <input type="checkbox" aria-label={`Pick ${o.name}`} checked={picked.has(o.id)} onChange={() => toggle(o.id)} />}</td>
                    <td><a href={o.console_url} target="_blank" rel="noreferrer"><strong>{o.name}</strong></a></td>
                    <td>{o.plan_name}<br /><span className={`badge ${statusTone(o.status)}`}>{o.status_name}</span></td>
                    <td>{day(o.subscription_ends) || "—"}</td>
                    <td>{o.owner_name}<br /><span className="muted small">{o.owner_email}</span></td>
                    <td>{o.crm_account_id ? <Link to={`/clients/${o.crm_account_id}`}>{o.crm_account_name}</Link> : <span className="muted">Not yet</span>}</td>
                  </tr>
                ))}</tbody>
              </>
            ) : (
              <>
                <thead><tr><th scope="col"><span className="sr-only">Pick</span></th><th scope="col">Organization</th><th scope="col">Asked for</th><th scope="col">Contact</th><th scope="col">Received</th><th scope="col">In the CRM</th></tr></thead>
                <tbody>{(reqs ?? []).map((r) => (
                  <tr key={r.id}>
                    <td>{!r.crm_account_id && can("geohub.link") && <input type="checkbox" aria-label={`Pick ${r.organization}`} checked={picked.has(r.id)} onChange={() => toggle(r.id)} />}</td>
                    <td><strong>{r.organization}</strong>{r.message && <><br /><span className="muted small clamp">{r.message}</span></>}</td>
                    <td>{ASKED[r.plan] ?? r.plan}{r.team_size && <><br /><span className="muted small">Team: {r.team_size}</span></>}<br /><span className="badge">{REQ_STATUS[r.status] ?? r.status}</span></td>
                    <td>{r.contact_name}<br /><span className="small"><a href={`mailto:${r.email}`}>{r.email}</a>{r.phone && <> · <a href={`tel:${r.phone.replace(/\s/g, "")}`}>{r.phone}</a></>}</span></td>
                    <td>{day(r.created_at)}</td>
                    <td>{r.crm_account_id ? <Link to={`/clients/${r.crm_account_id}`}>{r.crm_account_name}</Link> : <span className="muted">Not yet</span>}</td>
                  </tr>
                ))}</tbody>
              </>
            )}
          </table>
        </div>
      )}
      <p className="muted small">A request comes in as a lead, with a deal and a task to contact them. A customer comes in with its owner as the main contact, linked to its organization on Geohub.</p>
    </div>
  );
}
