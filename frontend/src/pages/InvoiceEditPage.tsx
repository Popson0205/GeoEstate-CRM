import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Button, ErrorText, useAction } from "../components/ui";
import { api } from "../lib/api";
import { PRODUCTS, PRODUCT_NAME, invoiceTotals, licenceTitle, naira2, nextStart, planName, yearFrom } from "../lib/format";
import type { Account, AccountDetail, GeohubOrg, InvoiceDraft, LicencePlan, Line, Price, Product } from "../lib/types";

const longDay = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
export const licenceLine = (product: Product, plan: LicencePlan, starts: string, ends: string) =>
  `${licenceTitle(product, plan)} licence, one year (${longDay(starts)} to ${longDay(ends)})`;
/** When the client's licence for a product ends on Geohub, if it has one. */
const endsOn = (org: GeohubOrg | null, product: Product) =>
  !org ? null : product === "hub" ? org.subscription_ends : org.products?.find((p) => p.product === product)?.subscription_ends ?? null;
const blank = (): Line => ({ description: "", quantity: "1", unit_price_ngn: "" });

/** A new invoice, or a draft being changed: the client, the Geohub licence it pays for, the lines, VAT, notes. */
export default function InvoiceEditPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { busy, run } = useAction();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [prices, setPrices] = useState<Price[]>([]);
  const [vat, setVat] = useState(7.5);
  const [client, setClient] = useState<AccountDetail | null>(null);
  const [org, setOrg] = useState<GeohubOrg | null>(null);
  const [f, setF] = useState<InvoiceDraft>({ account_id: params.get("client") ?? "", deal_id: params.get("deal"), lines: [blank()], notes: "",
    licence_product: "hub", licence_plan: null, licence_starts: null, licence_ends: null });
  const [auto, setAuto] = useState(false);              // the first line is the licence line we wrote
  const [error, setError] = useState<unknown>(null);
  const [loaded, setLoaded] = useState(!id);

  useEffect(() => {
    void api.accounts({}).then(setAccounts, setError);
    void api.prices().then(setPrices, () => setPrices([]));
    void api.company().then((c) => setVat(c.vat_rate), () => undefined);
    if (id) void api.invoice(id).then((inv) => {
      if (inv.status !== "draft") { nav(`/invoices/${id}`, { replace: true }); return; }
      setF({ account_id: inv.account_id, deal_id: inv.deal_id, notes: inv.notes, licence_product: inv.licence_product, licence_plan: inv.licence_plan, licence_starts: inv.licence_starts,
        licence_ends: inv.licence_ends, lines: inv.lines.map((l) => ({ description: l.description, quantity: String(Number(l.quantity)), unit_price_ngn: String(Number(l.unit_price_ngn)) })) });
      setLoaded(true);
    }, setError);
  }, [id]);

  useEffect(() => {
    setClient(null); setOrg(null);
    if (!f.account_id) return;
    void api.account(f.account_id).then(setClient, setError);
    void api.accountGeohub(f.account_id).then((g) => setOrg(g.org), () => setOrg(null));
  }, [f.account_id]);

  const t = useMemo(() => invoiceTotals(f.lines, vat), [f.lines, vat]);
  const price = (p: LicencePlan, product: Product = f.licence_product) => prices.find((x) => x.plan === p && x.product === product)?.amount_ngn ?? "";

  function chooseLicence(plan: LicencePlan | null, product: Product = f.licence_product) {
    if (!plan) {
      setF((x) => ({ ...x, licence_plan: null, licence_starts: null, licence_ends: null, lines: auto && x.lines.length > 1 ? x.lines.slice(1) : auto ? [blank()] : x.lines }));
      setAuto(false); return;
    }
    const fresh = product !== f.licence_product;
    const starts = (!fresh && f.licence_starts) || nextStart(endsOn(org, product));
    const ends = (!fresh && f.licence_ends) || yearFrom(starts);
    const amount = price(plan, product);
    const line = { description: licenceLine(product, plan, starts, ends), quantity: "1", unit_price_ngn: amount ? String(Number(amount)) : "" };
    setF((x) => {
      const keep = auto ? x.lines.slice(1) : x.lines.filter((l) => l.description.trim() || l.unit_price_ngn);
      return { ...x, licence_product: product, licence_plan: plan, licence_starts: starts, licence_ends: ends, lines: [line, ...keep] };
    });
    setAuto(true);
  }
  function setDates(starts: string, ends: string) {
    setF((x) => ({ ...x, licence_starts: starts, licence_ends: ends,
      lines: auto && x.licence_plan && starts && ends ? [{ ...x.lines[0], description: licenceLine(x.licence_product, x.licence_plan, starts, ends) }, ...x.lines.slice(1)] : x.lines }));
  }
  const setLine = (i: number, l: Partial<Line>) => { if (i === 0 && l.description !== undefined) setAuto(false); setF((x) => ({ ...x, lines: x.lines.map((y, j) => (j === i ? { ...y, ...l } : y)) })); };

  async function save(e: FormEvent) {
    e.preventDefault();
    const body = { ...f, deal_id: f.deal_id || null, lines: f.lines.filter((l) => l.description.trim()) };
    const saved = id ? await run("save", () => api.updateInvoice(id, { ...body, clear_licence: !body.licence_plan }), "Draft saved.")
      : await run("save", () => api.createInvoice(body), "Draft invoice made.");
    if (saved) nav(`/invoices/${saved.id}`);
  }

  const now = org && (f.licence_product === "hub" ? { plan_name: org.plan_name, status_name: org.status_name, subscription_ends: org.subscription_ends }
    : org.products?.find((x) => x.product === f.licence_product));
  const status = !client ? "" : !client.geohub_org_id ? "This client is not on Geohub yet: set it up once the invoice is paid."
    : !org ? "" : now ? `${client.name} is on ${now.plan_name} (${(now.status_name ?? "").toLowerCase()})${now.subscription_ends ? ` until ${longDay(now.subscription_ends)}` : ""}, so a renewal starts the day after.`
    : `${client.name} does not have ${PRODUCT_NAME[f.licence_product]} yet: it starts from today.`;

  if (!loaded) return <div className="page">{error ? <ErrorText error={error} /> : <p className="loading">Loading…</p>}</div>;
  return (
    <div className="page">
      <Link to={id ? `/invoices/${id}` : "/invoices"} className="back">{id ? "Back to the invoice" : "All invoices"}</Link>
      <h1>{id ? "Change the draft" : "New invoice"}</h1>
      <ErrorText error={error} />
      <form className="stack" onSubmit={save}>
        <section className="card grid-form" aria-label="Client">
          <div className="field"><label htmlFor="i-client">Client</label>
            <select id="i-client" required value={f.account_id} disabled={!!id} onChange={(e) => setF({ ...f, account_id: e.target.value, deal_id: null })}>
              <option value="">Choose a client</option>
              {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select></div>
          <div className="field"><label htmlFor="i-deal">Deal (optional)</label>
            <select id="i-deal" value={f.deal_id ?? ""} onChange={(e) => setF({ ...f, deal_id: e.target.value || null })} disabled={!client}>
              <option value="">None</option>
              {client?.deals.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
            </select></div>
          {client && <p className="wide muted small">
            Billed to {client.name}{client.contacts[0] ? `, attention ${client.contacts[0].name}` : ""}{client.contacts[0]?.email ? ` (${client.contacts[0].email})` : ""}.
            {!client.contacts.some((c) => c.email) && !client.email && " Add a contact with an email to send it by email."}
          </p>}
        </section>

        <section className="card" aria-labelledby="lic-h">
          <h2 id="lic-h">Licence</h2>
          <p className="muted small">When this invoice is paid in full, the licence is switched on in {PRODUCT_NAME[f.licence_product]} through Geohub. {status}</p>
          <div className="field" style={{ maxWidth: 320, marginBottom: 12 }}><label htmlFor="i-product">Product</label>
            <select id="i-product" value={f.licence_product} onChange={(e) => {
              const product = e.target.value as Product;
              if (f.licence_plan) chooseLicence(f.licence_plan, product); else setF({ ...f, licence_product: product });
            }}>{PRODUCTS.map((k) => <option key={k} value={k}>{PRODUCT_NAME[k]}</option>)}</select></div>
          <div className="seg" role="radiogroup" aria-label="Licence">
            {([null, "standard", "advanced", "custom"] as const).map((p) => (
              <label key={p ?? "none"} className={f.licence_plan === p ? "is-on" : ""}>
                <input type="radio" name="licence" checked={f.licence_plan === p} onChange={() => chooseLicence(p)} />
                {p ? `${planName(f.licence_product, p)}${price(p) ? ` · ${naira2(price(p))}` : ""}` : "No licence"}
              </label>
            ))}
          </div>
          {f.licence_plan && !price(f.licence_plan) && <p className="muted small">No price is set for {planName(f.licence_product, f.licence_plan)}: type it on the line below, or set it under Invoices → Prices.</p>}
          {f.licence_plan && (
            <div className="row" style={{ marginTop: 12 }}>
              <div className="field"><label htmlFor="i-from">From</label><input id="i-from" type="date" required value={f.licence_starts ?? ""} onChange={(e) => setDates(e.target.value, e.target.value ? yearFrom(e.target.value) : "")} /></div>
              <div className="field"><label htmlFor="i-to">To</label><input id="i-to" type="date" required min={f.licence_starts ?? undefined} value={f.licence_ends ?? ""} onChange={(e) => setDates(f.licence_starts ?? "", e.target.value)} /></div>
            </div>
          )}
        </section>

        <section className="card" aria-labelledby="lines-h">
          <h2 id="lines-h">What it is for</h2>
          <div className="lines">
            <div className="line line-head" aria-hidden="true"><span>Description</span><span>Qty</span><span>Unit price (₦)</span><span className="r">Amount</span><span /></div>
            {f.lines.map((l, i) => (
              <div className="line" key={i}>
                <div className="field"><label htmlFor={`l-d-${i}`} className="sr-only">Line {i + 1} description</label>
                  <textarea id={`l-d-${i}`} rows={Math.min(4, Math.max(1, Math.ceil(l.description.length / 44)))} required={i === 0} value={l.description} onChange={(e) => setLine(i, { description: e.target.value })} placeholder="What the client pays for" /></div>
                <div className="field"><label htmlFor={`l-q-${i}`} className="sr-only">Line {i + 1} quantity</label>
                  <input id={`l-q-${i}`} type="number" min="0.01" step="0.01" required value={l.quantity} onChange={(e) => setLine(i, { quantity: e.target.value })} /></div>
                <div className="field"><label htmlFor={`l-p-${i}`} className="sr-only">Line {i + 1} unit price</label>
                  <input id={`l-p-${i}`} type="number" min="0" step="0.01" required={!!l.description.trim()} value={l.unit_price_ngn} onChange={(e) => setLine(i, { unit_price_ngn: e.target.value })} /></div>
                <span className="num r">{naira2(t.amounts[i])}</span>
                <Button small variant="ghost" aria-label={`Remove line ${i + 1}`} disabled={f.lines.length === 1}
                  onClick={() => { if (i === 0) setAuto(false); setF({ ...f, lines: f.lines.filter((_, j) => j !== i) }); }}>Remove</Button>
              </div>
            ))}
          </div>
          <Button small onClick={() => setF({ ...f, lines: [...f.lines, blank()] })}>Add a line</Button>
          <dl className="totals">
            <dt>Subtotal</dt><dd>{naira2(t.subtotal)}</dd>
            <dt>VAT ({vat}%)</dt><dd>{naira2(t.vat)}</dd>
            <dt>Total</dt><dd><strong>{naira2(t.total)}</strong></dd>
          </dl>
        </section>

        <section className="card">
          <div className="field"><label htmlFor="i-notes">Notes on the invoice (optional)</label>
            <textarea id="i-notes" rows={2} maxLength={4000} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} placeholder="e.g. Thank you for choosing Geohub." /></div>
        </section>
        <div className="actions">
          <Button type="submit" variant="primary" busy={busy === "save"}>Save draft</Button>
          <span className="muted small">A draft has no number yet. Issue it to give it one and send it.</span>
        </div>
      </form>
    </div>
  );
}
