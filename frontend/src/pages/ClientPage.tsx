import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ActivityList, AddActivity } from "../components/Activities";
import GeohubCard from "../components/GeohubCard";
import InvoiceTable from "../components/InvoiceTable";
import { DealForm } from "./DealsPage";
import { Button, ErrorText, useAction } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { PLAN_LABEL, STAGE_LABEL, STATUS_LABEL, day, naira } from "../lib/format";
import type { AccountDetail, AccountStatus, Contact, StaffBrief } from "../lib/types";

const FIELDS: [keyof AccountDetail, string][] = [["industry", "Industry"], ["email", "Email"], ["phone", "Phone"], ["website", "Website"],
  ["address", "Address"], ["city", "City"], ["state", "State"], ["country", "Country"], ["tin", "TIN"]];

export default function ClientPage() {
  const { id = "" } = useParams();
  const { can } = useAuth();
  const nav = useNavigate();
  const { busy, run } = useAction();
  const [a, setA] = useState<AccountDetail | null>(null);
  const [staff, setStaff] = useState<StaffBrief[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Partial<AccountDetail>>({});
  const [contact, setContact] = useState<Partial<Contact> | null>(null);
  const [newDeal, setNewDeal] = useState(false);

  const load = () => void api.account(id).then(setA, setError);
  useEffect(() => { load(); void api.staffBrief().then(setStaff, () => setStaff([])); }, [id]);

  if (error) return <div className="page"><ErrorText error={error} /></div>;
  if (!a) return <p className="loading">Loading…</p>;
  const edit = can("accounts.edit");

  async function save(e: FormEvent) {
    e.preventDefault();
    const { name, industry, email, phone, website, address, city, state, country, tin, status, owner_id, notes } = draft as AccountDetail;
    if (await run("save", () => api.updateAccount(a!.id, { name, industry, email, phone, website, address, city, state, country, tin, status, owner_id, notes }), "Saved.")) {
      setEditing(false); load();
    }
  }
  async function saveContact(e: FormEvent) {
    e.preventDefault();
    const c = contact!;
    const body = { name: c.name, title: c.title, email: c.email, phone: c.phone, is_primary: c.is_primary };
    if (await run("contact", () => (c.id ? api.updateContact(c.id, body) : api.addContact(a!.id, body)), c.id ? "Contact saved." : "Contact added.")) {
      setContact(null); load();
    }
  }

  return (
    <div className="page">
      <Link to="/clients" className="back">All clients</Link>
      <div className="head">
        <h1>{a.name} <span className={`badge s-${a.status}`}>{STATUS_LABEL[a.status]}</span></h1>
        <div className="actions">
          {edit && !editing && <Button onClick={() => { setDraft(a); setEditing(true); }}>Edit</Button>}
          {can("records.delete") && <Button variant="ghost" busy={busy === "del"} onClick={() => {
            if (window.confirm(`Delete ${a.name} with its contacts, deals and activity? This cannot be undone.`)) void run("del", () => api.deleteAccount(a.id), "Client deleted.").then(() => nav("/clients"));
          }}>Delete</Button>}
        </div>
      </div>

      <div className="two">
        <section className="card">
          <h2>Details</h2>
          {editing ? (
            <form className="grid-form" onSubmit={save}>
              <div className="field wide"><label htmlFor="e-name">Name</label><input id="e-name" required value={draft.name ?? ""} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></div>
              {FIELDS.map(([k, label]) => (
                <div className="field" key={k}><label htmlFor={`e-${k}`}>{label}</label><input id={`e-${k}`} value={String(draft[k] ?? "")} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} /></div>
              ))}
              <div className="field"><label htmlFor="e-status">Status</label>
                <select id="e-status" value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value as AccountStatus })}>
                  {(Object.keys(STATUS_LABEL) as AccountStatus[]).map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
                </select></div>
              <div className="field"><label htmlFor="e-owner">Account manager</label>
                <select id="e-owner" value={draft.owner_id ?? ""} onChange={(e) => setDraft({ ...draft, owner_id: e.target.value || null })}>
                  <option value="">Nobody</option>{staff.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select></div>
              <div className="field wide"><label htmlFor="e-notes">Notes</label><textarea id="e-notes" rows={3} value={draft.notes ?? ""} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} /></div>
              <div className="actions wide"><Button type="submit" variant="primary" busy={busy === "save"}>Save</Button><Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button></div>
            </form>
          ) : (
            <dl className="kv">
              <dt>Account manager</dt><dd>{a.owner_name ?? "Nobody"}</dd>
              {FIELDS.filter(([k]) => a[k]).map(([k, label]) => (
                <div key={k} className="kv-row"><dt>{label}</dt><dd>{k === "email" ? <a href={`mailto:${a.email}`}>{a.email}</a> : k === "phone" ? <a href={`tel:${a.phone.replace(/\s/g, "")}`}>{a.phone}</a> : String(a[k])}</dd></div>
              ))}
              {a.notes && <><dt>Notes</dt><dd className="pre">{a.notes}</dd></>}
              <dt>Client since</dt><dd>{day(a.created_at)}</dd>
            </dl>
          )}
        </section>

        <section className="card">
          <div className="head"><h2>Contacts</h2>{can("contacts.edit") && !contact && <Button small onClick={() => setContact({ name: "", is_primary: a.contacts.length === 0 })}>Add a contact</Button>}</div>
          {contact && (
            <form className="grid-form" onSubmit={saveContact} aria-label="Contact">
              <div className="field"><label htmlFor="ct-name">Name</label><input id="ct-name" required value={contact.name ?? ""} onChange={(e) => setContact({ ...contact, name: e.target.value })} /></div>
              <div className="field"><label htmlFor="ct-title">Job title</label><input id="ct-title" value={contact.title ?? ""} onChange={(e) => setContact({ ...contact, title: e.target.value })} /></div>
              <div className="field"><label htmlFor="ct-email">Email</label><input id="ct-email" type="email" value={contact.email ?? ""} onChange={(e) => setContact({ ...contact, email: e.target.value })} /></div>
              <div className="field"><label htmlFor="ct-phone">Phone</label><input id="ct-phone" value={contact.phone ?? ""} onChange={(e) => setContact({ ...contact, phone: e.target.value })} /></div>
              <label className="check wide"><input type="checkbox" checked={!!contact.is_primary} onChange={(e) => setContact({ ...contact, is_primary: e.target.checked })} />Main contact</label>
              <div className="actions wide"><Button type="submit" variant="primary" busy={busy === "contact"}>Save contact</Button><Button variant="ghost" onClick={() => setContact(null)}>Cancel</Button></div>
            </form>
          )}
          {a.contacts.length === 0 ? <p className="muted">No contacts yet.</p> : (
            <ul className="contacts">
              {a.contacts.map((c) => (
                <li key={c.id}>
                  <div><strong>{c.name}</strong>{c.is_primary && <span className="badge">Main</span>}{c.title && <span className="muted"> · {c.title}</span>}<br />
                    <span className="small">{c.email && <a href={`mailto:${c.email}`}>{c.email}</a>}{c.email && c.phone && " · "}{c.phone && <a href={`tel:${c.phone.replace(/\s/g, "")}`}>{c.phone}</a>}</span></div>
                  {can("contacts.edit") && <span className="actions">
                    <Button small variant="ghost" onClick={() => setContact(c)} aria-label={`Edit ${c.name}`}>Edit</Button>
                    <Button small variant="ghost" busy={busy === c.id} aria-label={`Remove ${c.name}`} onClick={() => { if (window.confirm(`Remove ${c.name}?`)) void run(c.id, () => api.deleteContact(c.id), "Contact removed.").then(load); }}>Remove</Button>
                  </span>}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <div className="two">
        <GeohubCard a={a} onChange={load} />
        <section className="card" aria-labelledby="inv-h">
          <div className="head"><h2 id="inv-h">Invoices</h2>{can("invoices.edit") && <Link className="btn btn-sm" to={`/invoices/new?client=${a.id}`}>New invoice</Link>}</div>
          {a.invoices.length === 0 ? <p className="muted">No invoices yet.</p> : <InvoiceTable items={a.invoices} showClient={false} />}
        </section>
      </div>

      <section className="card">
        <div className="head"><h2>Deals</h2>{can("deals.edit") && !newDeal && <Button small onClick={() => setNewDeal(true)}>Add a deal</Button>}</div>
        {newDeal && <DealForm staff={staff} accountId={a.id} onDone={(saved) => { setNewDeal(false); if (saved) load(); }} />}
        {a.deals.length === 0 ? <p className="muted">No deals yet.</p> : (
          <div className="table-wrap"><table className="table">
            <thead><tr><th scope="col">Deal</th><th scope="col">Stage</th><th scope="col">Amount (before VAT)</th><th scope="col">Expected</th><th scope="col">Owner</th></tr></thead>
            <tbody>{a.deals.map((d) => (
              <tr key={d.id}><td><Link to={`/deals?focus=${d.id}`}><strong>{d.title}</strong></Link><br /><span className="muted small">{PLAN_LABEL[d.plan]}</span></td>
                <td><span className={`badge st-${d.stage}`}>{STAGE_LABEL[d.stage]}</span>{d.stage === "lost" && d.lost_reason && <><br /><span className="muted small">{d.lost_reason}</span></>}</td>
                <td className="num">{naira(d.amount_ngn)}</td><td>{day(d.expected_close) || "—"}</td><td>{d.owner_name ?? "—"}</td></tr>
            ))}</tbody>
          </table></div>
        )}
      </section>

      <section className="card">
        <h2>Activity</h2>
        {can("activities.edit") && <AddActivity staff={staff} accountId={a.id} onAdded={load} />}
        <ActivityList items={a.activities} onChange={load} showClient={false} />
      </section>
    </div>
  );
}
