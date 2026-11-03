import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button, ErrorText, useAction } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { STATUS_LABEL, day, naira } from "../lib/format";
import type { Account, AccountStatus } from "../lib/types";

export default function ClientsPage() {
  const { can } = useAuth();
  const nav = useNavigate();
  const { busy, run } = useAction();
  const [list, setList] = useState<Account[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<AccountStatus | "">("");
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState({ name: "", industry: "", email: "", phone: "", city: "", state: "" });

  const load = (s = status, query = q) => void api.accounts({ q: query.trim() || undefined, status: s || undefined }).then(setList, setError);
  useEffect(() => load(), []);   // filters reload on change below

  async function add(e: FormEvent) {
    e.preventDefault();
    const a = await run("add", () => api.createAccount(f), "Client added.");
    if (a) nav(`/clients/${a.id}`);
  }

  return (
    <div className="page">
      <div className="head"><h1>Clients</h1>{can("accounts.edit") && !adding && <Button variant="primary" onClick={() => setAdding(true)}>Add a client</Button>}</div>
      {adding && (
        <form className="card grid-form" onSubmit={add} aria-label="New client">
          <div className="field wide"><label htmlFor="c-name">Name</label><input id="c-name" required maxLength={200} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
          <div className="field"><label htmlFor="c-industry">Industry</label><input id="c-industry" value={f.industry} onChange={(e) => setF({ ...f, industry: e.target.value })} placeholder="e.g. Surveying, Government, NGO" /></div>
          <div className="field"><label htmlFor="c-email">Email</label><input id="c-email" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
          <div className="field"><label htmlFor="c-phone">Phone</label><input id="c-phone" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></div>
          <div className="field"><label htmlFor="c-city">City</label><input id="c-city" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} /></div>
          <div className="field"><label htmlFor="c-state">State</label><input id="c-state" value={f.state} onChange={(e) => setF({ ...f, state: e.target.value })} /></div>
          <div className="actions wide"><Button type="submit" variant="primary" busy={busy === "add"}>Add client</Button><Button variant="ghost" onClick={() => setAdding(false)}>Cancel</Button></div>
        </form>
      )}
      <div className="toolbar">
        <form role="search" onSubmit={(e) => { e.preventDefault(); load(); }}>
          <label htmlFor="q" className="sr-only">Search clients</label>
          <input id="q" type="search" placeholder="Search by name, city, contact or email" value={q} onChange={(e) => { setQ(e.target.value); if (!e.target.value) load(status, ""); }} />
        </form>
        <div className="chips" role="group" aria-label="Status">
          {(["", "lead", "customer", "former"] as const).map((s) => (
            <button key={s} type="button" className={`chip${status === s ? " is-on" : ""}`} aria-pressed={status === s} onClick={() => { setStatus(s); load(s); }}>
              {s ? STATUS_LABEL[s] : "All"}</button>
          ))}
        </div>
      </div>
      <ErrorText error={error} />
      {!list ? <p className="loading">Loading…</p> : list.length === 0 ? <p className="muted">No clients {q || status ? "match" : "yet"}.</p> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th scope="col">Client</th><th scope="col">Status</th><th scope="col">Open deals</th><th scope="col">Account manager</th><th scope="col">Updated</th></tr></thead>
            <tbody>
              {list.map((a) => (
                <tr key={a.id}>
                  <td><Link to={`/clients/${a.id}`}><strong>{a.name}</strong></Link><br /><span className="muted small">{[a.primary_contact, a.city, a.industry].filter(Boolean).join(" · ")}</span></td>
                  <td><span className={`badge s-${a.status}`}>{STATUS_LABEL[a.status]}</span></td>
                  <td className="num">{a.open_deals ? `${a.open_deals} · ${naira(a.open_value_ngn)}` : "—"}</td>
                  <td>{a.owner_name ?? "—"}</td>
                  <td className="muted">{day(a.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
