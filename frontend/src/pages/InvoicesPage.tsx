import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import InvoiceTable from "../components/InvoiceTable";
import { Button, ErrorText, useAction } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { PRODUCTS, PRODUCT_NAME, day, naira, naira2, planName } from "../lib/format";
import type { Invoice, LicencePlan, Price, Product, Terms } from "../lib/types";

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
      <TermsCard />
    </div>
  );
}

/** What a year of each product's plans costs; super admins set them. */
const FILL: Record<string, string> = { number: "GE-2026-0001", issue_date: "7 November 2026", due_date: "21 November 2026",
  company: "the company", email: "the company email" };
const filled = (body: string) => body.replace(/\{(number|issue_date|due_date|company|email)\}/g, (_, k: string) => FILL[k]);

/** The terms and conditions printed on every invoice. Invoices already issued keep the terms they went out with. */
function TermsCard() {
  const { can } = useAuth();
  const { busy, run } = useAction();
  const [terms, setTerms] = useState<Terms | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  useEffect(() => void api.terms().then(setTerms, () => setTerms(null)), []);
  async function save(e: FormEvent) {
    e.preventDefault();
    const t = await run("terms", () => api.setTerms(draft!), "Terms saved. They print on drafts and on invoices issued from now on.");
    if (t) { setTerms(t); setDraft(null); }
  }
  return (
    <section className="card" style={{ marginTop: 18 }} aria-labelledby="terms-h">
      <div className="head"><h2 id="terms-h">Terms and conditions</h2>
        {can("prices.edit") && terms && draft === null && <div className="actions"><Button small onClick={() => setDraft(terms.body)}>Change</Button></div>}</div>
      <p className="muted small">Printed at the end of every invoice. An issued invoice keeps the terms it was sent with, so a change here applies to
        drafts and to invoices issued from now on.{terms?.updated_by_name ? ` Last changed by ${terms.updated_by_name}, ${day(terms.updated_at)}.` : ""}</p>
      {draft !== null ? (
        <form onSubmit={save} className="stack">
          <div className="field"><label htmlFor="terms-body">One paragraph per line</label>
            <textarea id="terms-body" rows={14} maxLength={8000} required value={draft} onChange={(e) => setDraft(e.target.value)} /></div>
          <p className="muted small">On each invoice, <code>{"{number}"}</code>, <code>{"{issue_date}"}</code>, <code>{"{due_date}"}</code>,
            {" "}<code>{"{company}"}</code> and <code>{"{email}"}</code> become that invoice's number and dates and GeoEstate's name and email.</p>
          <div className="actions"><Button type="submit" variant="primary" busy={busy === "terms"}>Save terms</Button>
            <Button variant="ghost" onClick={() => setDraft(null)}>Cancel</Button></div>
        </form>
      ) : terms ? <ol className="terms">{filled(terms.body).split("\n").filter((l) => l.trim()).map((l, i) => <li key={i}>{l.replace(/^\d+\.\s*/, "")}</li>)}</ol>
        : <p className="muted">No terms are set.</p>}
    </section>
  );
}

function Prices() {
  const { can } = useAuth();
  const { busy, run } = useAction();
  const [prices, setPrices] = useState<Price[]>([]);
  const [edit, setEdit] = useState<Record<string, string> | null>(null);
  const [add, setAdd] = useState<{ product: Product; plan: LicencePlan; amount: string } | null>(null);
  const key = (p: Price) => `${p.product}/${p.plan}`;
  const load = () => void api.prices().then(setPrices, () => setPrices([]));
  useEffect(load, []);
  async function save(e: FormEvent) {
    e.preventDefault();
    for (const p of prices) {
      const v = edit![key(p)];
      if (v !== undefined && Number(v) !== Number(p.amount_ngn) && !await run("prices", () => api.setPrice(p.product, p.plan, v))) return;
    }
    setEdit(null); load();
  }
  async function addPrice(e: FormEvent) {
    e.preventDefault();
    if (await run("add", () => api.setPrice(add!.product, add!.plan, add!.amount), `${planName(add!.product, add!.plan)} is priced.`)) { setAdd(null); load(); }
  }
  const groups = PRODUCTS.map((k) => ({ product: k, items: prices.filter((p) => p.product === k) })).filter((g) => g.items.length);
  return (
    <section className="card" style={{ marginTop: 18 }} aria-labelledby="prices-h">
      <div className="head"><h2 id="prices-h">Prices</h2>
        {can("prices.edit") && !edit && !add && <div className="actions">
          <Button small onClick={() => setEdit(Object.fromEntries(prices.map((p) => [key(p), String(Number(p.amount_ngn))])))}>Change</Button>
          <Button small onClick={() => setAdd({ product: "land", plan: "standard", amount: "" })}>Add a price</Button>
        </div>}
      </div>
      <p className="muted small">A year of each plan, before 7.5% VAT. New invoices start from these; a plan without a price is typed on the invoice.</p>
      {add && (
        <form className="row" onSubmit={addPrice} aria-label="Add a price" style={{ marginBottom: 12 }}>
          <div className="field"><label htmlFor="np-product">Product</label>
            <select id="np-product" value={add.product} onChange={(e) => setAdd({ ...add, product: e.target.value as Product })}>{PRODUCTS.map((k) => <option key={k} value={k}>{PRODUCT_NAME[k]}</option>)}</select></div>
          <div className="field"><label htmlFor="np-plan">Plan</label>
            <select id="np-plan" value={add.plan} onChange={(e) => setAdd({ ...add, plan: e.target.value as LicencePlan })}>
              <option value="standard">Standard</option><option value="advanced">Advanced</option><option value="custom">Custom</option></select></div>
          <div className="field"><label htmlFor="np-amount">A year (₦, before VAT)</label>
            <input id="np-amount" type="number" min="0" step="0.01" required value={add.amount} onChange={(e) => setAdd({ ...add, amount: e.target.value })} /></div>
          <div className="actions"><Button type="submit" variant="primary" busy={busy === "add"}>Save price</Button><Button variant="ghost" onClick={() => setAdd(null)}>Cancel</Button></div>
        </form>
      )}
      {edit ? (
        <form className="row" onSubmit={save}>
          {prices.map((p) => (
            <div className="field" key={key(p)}><label htmlFor={`price-${p.product}-${p.plan}`}>{planName(p.product, p.plan)} (₦)</label>
              <input id={`price-${p.product}-${p.plan}`} type="number" min="0" step="0.01" required value={edit[key(p)]} onChange={(e) => setEdit({ ...edit, [key(p)]: e.target.value })} /></div>
          ))}
          <div className="actions"><Button type="submit" variant="primary" busy={busy === "prices"}>Save prices</Button><Button variant="ghost" onClick={() => setEdit(null)}>Cancel</Button></div>
        </form>
      ) : (
        <dl className="kv">
          {groups.map((g) => g.items.map((p) => <div className="kv-row" key={key(p)}><dt>{p.product === "hub" ? `Geohub ${planName(p.product, p.plan)}` : planName(p.product, p.plan)}</dt><dd><strong className="num">{naira(p.amount_ngn)}</strong>
            <span className="muted small"> a year · {naira(Number(p.amount_ngn) * 1.075)} with VAT{p.updated_by_name ? ` · set by ${p.updated_by_name}, ${day(p.updated_at)}` : ""}</span></dd></div>))}
        </dl>
      )}
    </section>
  );
}
