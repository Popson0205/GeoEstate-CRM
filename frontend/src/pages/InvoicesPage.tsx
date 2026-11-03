import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import InvoiceTable from "../components/InvoiceTable";
import { Button, ErrorText, useAction } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { day, naira, naira2 } from "../lib/format";
import type { Invoice, Price } from "../lib/types";

const FILTERS = [["unpaid", "Unpaid"], ["overdue", "Overdue"], ["draft", "Drafts"], ["paid", "Paid"], ["void", "Void"], ["", "All"]] as const;

export default function InvoicesPage() {
  const { can } = useAuth();
  const [list, setList] = useState<Invoice[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [status, setStatus] = useState<string>("unpaid");
  const [q, setQ] = useState("");
  const load = (s = status, query = q) => { setList(null); void api.invoices({ status: s || undefined, q: query.trim() || undefined }).then(setList, setError); };
  useEffect(() => load(), []);
  const owed = (list ?? []).reduce((s, i) => s + Number(i.balance_ngn), 0);

  return (
    <div className="page">
      <div className="head"><h1>Invoices</h1>{can("invoices.edit") && <Link className="btn btn-primary" to="/invoices/new">New invoice</Link>}</div>
      <div className="toolbar">
        <form role="search" onSubmit={(e) => { e.preventDefault(); load(); }}>
          <label htmlFor="iq" className="sr-only">Search invoices</label>
          <input id="iq" type="search" placeholder="Search by invoice number or client" value={q} onChange={(e) => { setQ(e.target.value); if (!e.target.value) load(status, ""); }} />
        </form>
        <div className="chips" role="group" aria-label="Show">
          {FILTERS.map(([id, label]) => (
            <button key={id} type="button" className={`chip${status === id ? " is-on" : ""}`} aria-pressed={status === id}
              onClick={() => { setStatus(id); load(id); }}>{label}</button>
          ))}
        </div>
      </div>
      <ErrorText error={error} />
      {!list ? <p className="loading">Loading…</p> : list.length === 0 ? <p className="muted">No invoices {q ? "match" : "here"}.</p> : (
        <>
          {(status === "unpaid" || status === "overdue") && <p className="muted">{status === "overdue" ? "Overdue" : "Still owed"}: <strong className="num">{naira2(owed)}</strong></p>}
          <InvoiceTable items={list} />
        </>
      )}
      <Prices />
    </div>
  );
}

/** What a year of each plan costs; super admins change it. */
function Prices() {
  const { can } = useAuth();
  const { busy, run } = useAction();
  const [prices, setPrices] = useState<Price[]>([]);
  const [edit, setEdit] = useState<Record<string, string> | null>(null);
  useEffect(() => { void api.prices().then(setPrices, () => setPrices([])); }, []);
  async function save(e: FormEvent) {
    e.preventDefault();
    for (const p of prices) {
      if (edit![p.plan] !== undefined && Number(edit![p.plan]) !== Number(p.amount_ngn)) {
        if (!await run("prices", () => api.setPrice(p.plan, edit![p.plan]))) return;
      }
    }
    setEdit(null); setPrices(await api.prices());
  }
  return (
    <section className="card" style={{ marginTop: 18 }} aria-labelledby="prices-h">
      <div className="head"><h2 id="prices-h">Prices</h2>{can("prices.edit") && !edit && <Button small onClick={() => setEdit(Object.fromEntries(prices.map((p) => [p.plan, String(Number(p.amount_ngn))])))}>Change</Button>}</div>
      <p className="muted small">A year of each plan, before 7.5% VAT. New invoices start from these.</p>
      {edit ? (
        <form className="row" onSubmit={save}>
          {prices.map((p) => (
            <div className="field" key={p.plan}><label htmlFor={`price-${p.plan}`}>{p.name} (₦)</label>
              <input id={`price-${p.plan}`} type="number" min="0" step="0.01" required value={edit[p.plan]} onChange={(e) => setEdit({ ...edit, [p.plan]: e.target.value })} /></div>
          ))}
          <div className="actions"><Button type="submit" variant="primary" busy={busy === "prices"}>Save prices</Button><Button variant="ghost" onClick={() => setEdit(null)}>Cancel</Button></div>
        </form>
      ) : (
        <dl className="kv">
          {prices.map((p) => <div className="kv-row" key={p.plan}><dt>{p.name}</dt><dd><strong className="num">{naira(p.amount_ngn)}</strong>
            <span className="muted small"> a year · {naira(Number(p.amount_ngn) * 1.075)} with VAT{p.updated_by_name ? ` · set by ${p.updated_by_name}, ${day(p.updated_at)}` : ""}</span></dd></div>)}
        </dl>
      )}
    </section>
  );
}
