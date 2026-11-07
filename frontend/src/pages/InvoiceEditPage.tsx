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
const PLANS: LicencePlan[] = ["standard", "advanced", "custom"];

/** A line being edited. `auto`: its description is the licence wording we wrote, so it follows the plan and dates. */
type EditLine = Line & { auto?: boolean };
const blank = (): EditLine => ({ description: "", quantity: "1", unit_price_ngn: "" });
const isLicence = (l: EditLine) => !!l.licence_product;
const isEmpty = (l: EditLine) => !l.licence_product && !l.description.trim() && !l.unit_price_ngn;

/** A new invoice, or a draft being changed: the client, the products it pays for (one licence each), any other lines
 *  such as training, VAT and notes. */
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
  const [orgKnown, setOrgKnown] = useState(false);       // the client's licences today are known, so renewals start after them
  const [f, setF] = useState<Omit<InvoiceDraft, "lines"> & { lines: EditLine[] }>({ account_id: params.get("client") ?? "", deal_id: params.get("deal"), lines: [blank()], notes: "" });
  const [error, setError] = useState<unknown>(null);
  const [loaded, setLoaded] = useState(!id);

  useEffect(() => {
    void api.accounts({}).then(setAccounts, setError);
    void api.prices().then(setPrices, () => setPrices([]));
    void api.company().then((c) => setVat(c.vat_rate), () => undefined);
    if (id) void api.invoice(id).then((inv) => {
      if (inv.status !== "draft") { nav(`/invoices/${id}`, { replace: true }); return; }
      const lines: EditLine[] = inv.lines.map((l) => {
        const lic = l.licence_product && l.licence_plan && l.licence_starts && l.licence_ends ? l : null;
        return { description: l.description, quantity: String(Number(l.quantity)), unit_price_ngn: String(Number(l.unit_price_ngn)),
          licence_product: l.licence_product ?? null, licence_plan: l.licence_plan ?? null, licence_starts: l.licence_starts ?? null,
          licence_ends: l.licence_ends ?? null,
          auto: !!lic && l.description === licenceLine(lic.licence_product!, lic.licence_plan!, lic.licence_starts!, lic.licence_ends!) };
      });
      setF({ account_id: inv.account_id, deal_id: inv.deal_id, notes: inv.notes, lines: lines.length ? lines : [blank()] });
      setLoaded(true);
    }, setError);
  }, [id]);

  useEffect(() => {
    setClient(null); setOrg(null); setOrgKnown(false);
    if (!f.account_id) return;
    void api.account(f.account_id).then(setClient, setError);
    void api.accountGeohub(f.account_id).then((g) => setOrg(g.org), () => setOrg(null)).finally(() => setOrgKnown(true));
  }, [f.account_id]);

  const t = useMemo(() => invoiceTotals(f.lines, vat), [f.lines, vat]);
  const price = (product: Product, p: LicencePlan) => prices.find((x) => x.plan === p && x.product === product)?.amount_ngn ?? "";
  const used = f.lines.filter(isLicence).map((l) => l.licence_product as Product);
  const free = PRODUCTS.filter((p) => !used.includes(p));

  /** The licence fields of line i, as they would be for this product and plan (dates kept unless the product changes). */
  function licenced(l: EditLine, product: Product, plan: LicencePlan): EditLine {
    const fresh = product !== l.licence_product;
    const starts = (!fresh && l.licence_starts) || nextStart(endsOn(org, product));
    const ends = (!fresh && l.licence_ends) || yearFrom(starts);
    const amount = price(product, plan);
    const priceChanges = fresh || plan !== l.licence_plan;
    return { ...l, licence_product: product, licence_plan: plan, licence_starts: starts, licence_ends: ends,
      unit_price_ngn: priceChanges ? (amount ? String(Number(amount)) : "") : l.unit_price_ngn,
      description: l.auto || !l.description.trim() ? licenceLine(product, plan, starts, ends) : l.description,
      auto: l.auto || !l.description.trim() };
  }
  function addProduct() {
    const product = free[0];
    if (!product) return;
    setF((x) => {
      const line = licenced(blank(), product, "standard");
      const rest = x.lines.filter((l) => !isEmpty(l));
      const at = rest.filter(isLicence).length;             // products first, then the other lines
      return { ...x, lines: [...rest.slice(0, at), line, ...rest.slice(at)] };
    });
  }
  const setLicence = (i: number, product: Product, plan: LicencePlan) =>
    setF((x) => ({ ...x, lines: x.lines.map((l, j) => (j === i ? licenced(l, product, plan) : l)) }));
  function setDates(i: number, starts: string, ends: string) {
    setF((x) => ({ ...x, lines: x.lines.map((l, j) => j !== i ? l : {
      ...l, licence_starts: starts, licence_ends: ends,
      description: l.auto && starts && ends ? licenceLine(l.licence_product!, l.licence_plan!, starts, ends) : l.description }) }));
  }
  const setLine = (i: number, l: Partial<EditLine>) =>
    setF((x) => ({ ...x, lines: x.lines.map((y, j) => (j === i ? { ...y, ...l, ...(l.description !== undefined ? { auto: false } : {}) } : y)) }));
  const removeLine = (i: number) => setF((x) => {
    const lines = x.lines.filter((_, j) => j !== i);
    return { ...x, lines: lines.length ? lines : [blank()] };
  });

  async function save(e: FormEvent) {
    e.preventDefault();
    const lines = f.lines.filter((l) => l.description.trim()).map(({ auto: _a, ...l }) => ({
      description: l.description, quantity: l.quantity, unit_price_ngn: l.unit_price_ngn,
      licence_product: l.licence_product ?? null, licence_plan: l.licence_product ? l.licence_plan ?? null : null,
      licence_starts: l.licence_product ? l.licence_starts ?? null : null, licence_ends: l.licence_product ? l.licence_ends ?? null : null }));
    const body = { ...f, deal_id: f.deal_id || null, lines };
    const saved = id ? await run("save", () => api.updateInvoice(id, { ...body, clear_licence: !lines.some((l) => l.licence_product) }), "Draft saved.")
      : await run("save", () => api.createInvoice(body), "Draft invoice made.");
    if (saved) nav(`/invoices/${saved.id}`);
  }

  const status = (product: Product) => {
    if (!client || !client.geohub_org_id || !org) return "";
    const now = product === "hub" ? { plan_name: org.plan_name, status_name: org.status_name, subscription_ends: org.subscription_ends }
      : org.products?.find((x) => x.product === product);
    return now ? `Now on ${now.plan_name} (${(now.status_name ?? "").toLowerCase()})${now.subscription_ends ? ` until ${longDay(now.subscription_ends)}` : ""}, so a renewal starts the day after.`
      : `${client.name} does not have ${PRODUCT_NAME[product]} yet: it starts from today.`;
  };
  const licences = f.lines.map((l, i) => [l, i] as const).filter(([l]) => isLicence(l));

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
          <h2 id="lic-h">Products</h2>
          <p className="muted small">Each product's licence is switched on through Geohub when the invoice is paid in full.
            {client && !client.geohub_org_id && " This client is not on Geohub yet: set it up once the invoice is paid."}</p>
          {licences.length === 0 && <p className="muted">No product on this invoice yet.</p>}
          <ul className="products">
            {licences.map(([l, i]) => {
              const product = l.licence_product as Product;
              const plan = (l.licence_plan ?? "standard") as LicencePlan;
              return (
                <li key={i} className="product-row" aria-label={`${PRODUCT_NAME[product]} licence`}>
                  <div className="field"><label htmlFor={`p-${i}`}>Product</label>
                    <select id={`p-${i}`} value={product} onChange={(e) => setLicence(i, e.target.value as Product, plan)}>
                      {PRODUCTS.filter((p) => p === product || !used.includes(p)).map((p) => <option key={p} value={p}>{PRODUCT_NAME[p]}</option>)}
                    </select></div>
                  <div className="field"><label htmlFor={`pl-${i}`}>Plan</label>
                    <select id={`pl-${i}`} value={plan} onChange={(e) => setLicence(i, product, e.target.value as LicencePlan)}>
                      {PLANS.map((p) => <option key={p} value={p}>{planName(product, p)}{price(product, p) ? ` · ${naira2(price(product, p))}` : ""}</option>)}
                    </select></div>
                  <div className="field"><label htmlFor={`pf-${i}`}>From</label>
                    <input id={`pf-${i}`} type="date" required value={l.licence_starts ?? ""} onChange={(e) => setDates(i, e.target.value, e.target.value ? yearFrom(e.target.value) : "")} /></div>
                  <div className="field"><label htmlFor={`pt-${i}`}>To</label>
                    <input id={`pt-${i}`} type="date" required min={l.licence_starts ?? undefined} value={l.licence_ends ?? ""} onChange={(e) => setDates(i, l.licence_starts ?? "", e.target.value)} /></div>
                  <Button small variant="ghost" aria-label={`Remove ${PRODUCT_NAME[product]}`} onClick={() => removeLine(i)}>Remove</Button>
                  <p className="muted small wide">{status(product)}{!price(product, plan) && ` No price is set for ${planName(product, plan)}: type it on its line below, or set it under Invoices → Prices.`}</p>
                </li>
              );
            })}
          </ul>
          <Button small onClick={addProduct} disabled={!free.length || !client || !orgKnown}>{free.length ? "+ Add a product" : "Every product is on this invoice"}</Button>
          {!f.account_id && <span className="muted small"> Choose the client first.</span>}
        </section>

        <section className="card" aria-labelledby="lines-h">
          <h2 id="lines-h">What it is for</h2>
          <p className="muted small">The products above have a line each. Add a line for anything else, such as training or a site visit.</p>
          <div className="lines">
            <div className="line line-head" aria-hidden="true"><span>Description</span><span>Qty</span><span>Unit price (₦)</span><span className="r">Amount</span><span /></div>
            {f.lines.map((l, i) => (
              <div className="line" key={i}>
                <div className="field"><label htmlFor={`l-d-${i}`} className="sr-only">Line {i + 1} description</label>
                  {isLicence(l) && <span className="tag">{PRODUCT_NAME[l.licence_product as Product]}</span>}
                  <textarea id={`l-d-${i}`} rows={Math.min(4, Math.max(1, Math.ceil(l.description.length / 44)))} required={i === 0 || isLicence(l)} value={l.description} onChange={(e) => setLine(i, { description: e.target.value })} placeholder="What the client pays for, e.g. Training, two days on site" /></div>
                <div className="field"><label htmlFor={`l-q-${i}`} className="sr-only">Line {i + 1} quantity</label>
                  <input id={`l-q-${i}`} type="number" min="0.01" step="0.01" required value={l.quantity} onChange={(e) => setLine(i, { quantity: e.target.value })} /></div>
                <div className="field"><label htmlFor={`l-p-${i}`} className="sr-only">Line {i + 1} unit price</label>
                  <input id={`l-p-${i}`} type="number" min="0" step="0.01" required={!!l.description.trim()} value={l.unit_price_ngn} onChange={(e) => setLine(i, { unit_price_ngn: e.target.value })} /></div>
                <span className="num r">{naira2(t.amounts[i])}</span>
                <Button small variant="ghost" aria-label={`Remove line ${i + 1}`} disabled={f.lines.length === 1 && !isLicence(l)} onClick={() => removeLine(i)}>Remove</Button>
              </div>
            ))}
          </div>
          <Button small onClick={() => setF({ ...f, lines: [...f.lines, blank()] })}>+ Add a line</Button>
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
