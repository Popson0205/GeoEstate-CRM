import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { InvoiceBadge } from "../components/InvoiceTable";
import { Button, ErrorText, useAction } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { PRODUCT_NAME, day, isoToday, licenceTitle, naira2, when } from "../lib/format";
import type { GeohubOrg, InvoiceDetail, Line, Product } from "../lib/types";

const METHOD: Record<string, string> = { bank_transfer: "Bank transfer", cash: "Cash", cheque: "Cheque", other: "Other" };

/** One invoice: what it says, its PDF, sending it, the money received, and the Geohub licence it pays for. */
export default function InvoicePage() {
  const { id = "" } = useParams();
  const { can } = useAuth();
  const nav = useNavigate();
  const { busy, run } = useAction();
  const [inv, setInv] = useState<InvoiceDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [org, setOrg] = useState<GeohubOrg | null>(null);
  const [panel, setPanel] = useState<"issue" | "email" | "pay" | "void" | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);

  const load = () => void api.invoice(id).then(setInv, setError);
  useEffect(load, [id]);
  useEffect(() => {
    if (!inv) return;
    let url: string | null = null;
    void api.invoicePdf(inv.id).then((b) => { url = URL.createObjectURL(b); setPdfUrl(url); }, () => setPdfUrl(null));
    if (inv.geohub_org_id) void api.accountGeohub(inv.account_id).then((g) => setOrg(g.org), () => setOrg(null));
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [inv]);

  if (error) return <div className="page"><ErrorText error={error} /></div>;
  if (!inv) return <p className="loading">Loading…</p>;
  const name = inv.number ?? "Draft invoice";
  const done = (x: InvoiceDetail | undefined) => { if (x) { setInv(x); setPanel(null); } };

  return (
    <div className="page page-wide invoice-page">
      <Link to="/invoices" className="back">All invoices</Link>
      <div className="head">
        <h1>{name} <InvoiceBadge i={inv} /></h1>
        <div className="actions">
          {inv.status === "draft" && can("invoices.edit") && <>
            <Button variant="primary" onClick={() => setPanel("issue")}>Issue</Button>
            <Link className="btn" to={`/invoices/${inv.id}/edit`}>Change</Link>
            <Button variant="ghost" busy={busy === "del"} onClick={() => {
              if (window.confirm("Delete this draft?")) void run("del", () => api.deleteInvoice(inv.id), "Draft deleted.").then(() => nav("/invoices"));
            }}>Delete</Button>
          </>}
          {inv.status === "issued" && can("payments.record") && <Button variant="primary" onClick={() => setPanel("pay")}>Record a payment</Button>}
          {(inv.status === "issued" || inv.status === "paid") && can("invoices.edit") && <Button onClick={() => setPanel("email")}>Email it</Button>}
          {pdfUrl && <a className="btn pdf-open" href={pdfUrl} target="_blank" rel="noreferrer">Open the PDF</a>}
          {pdfUrl && <a className="btn" href={pdfUrl} download={`${inv.number ?? "draft-invoice"}.pdf`}>Download PDF</a>}
          {inv.status === "issued" && Number(inv.paid_ngn) === 0 && can("payments.record") && <Button variant="ghost" onClick={() => setPanel("void")}>Void</Button>}
        </div>
      </div>

      {panel === "issue" && <IssueForm inv={inv} onDone={done} onCancel={() => setPanel(null)} />}
      {panel === "email" && <EmailForm inv={inv} onDone={done} onCancel={() => setPanel(null)} />}
      {panel === "pay" && <PaymentForm inv={inv} org={org} onDone={done} onCancel={() => setPanel(null)} />}
      {panel === "void" && <VoidForm inv={inv} onDone={done} onCancel={() => setPanel(null)} />}

      <div className="invoice-grid">
        <div>
          <section className="card">
            <dl className="kv">
              <dt>Client</dt><dd><Link to={`/clients/${inv.account_id}`}><strong>{inv.account_name}</strong></Link>{inv.bill_to.contact && <span className="muted"> · {inv.bill_to.contact}</span>}</dd>
              {inv.deal_title && <><dt>Deal</dt><dd>{inv.deal_title}</dd></>}
              <dt>Issued</dt><dd>{inv.issue_date ? day(inv.issue_date) : "Not yet"}</dd>
              {inv.due_date && <><dt>Due</dt><dd className={inv.overdue ? "late" : undefined}>{day(inv.due_date)}{inv.overdue && " (overdue)"}</dd></>}
              <dt>Total</dt><dd><strong className="num">{naira2(inv.total_ngn)}</strong> <span className="muted small">({naira2(inv.subtotal_ngn)} + {Number(inv.vat_rate)}% VAT {naira2(inv.vat_ngn)})</span></dd>
              {inv.status !== "draft" && inv.status !== "void" && <><dt>Still owed</dt><dd><strong className="num">{naira2(inv.balance_ngn)}</strong></dd></>}
              {inv.emailed_at && <><dt>Emailed</dt><dd>{when(inv.emailed_at)} to {inv.emailed_to}</dd></>}
              {inv.void_reason && <><dt>Voided</dt><dd>{inv.voided_at && when(inv.voided_at)}: {inv.void_reason}</dd></>}
              <dt>Made by</dt><dd>{inv.created_by_name ?? "—"}, {day(inv.created_at)}</dd>
            </dl>
          </section>

          {inv.licence_plan && <Licence inv={inv} org={org} onChange={setInv} />}

          <section className="card" aria-labelledby="pay-h">
            <h2 id="pay-h">Payments</h2>
            {inv.payments.length === 0 ? <p className="muted">{inv.status === "draft" ? "Issue the invoice first." : "Nothing received yet."}</p> : (
              <ul className="contacts">
                {inv.payments.map((p) => (
                  <li key={p.id}>
                    <div><strong className="num">{naira2(p.amount_ngn)}</strong> on {day(p.paid_on)}<br />
                      <span className="muted small">{[METHOD[p.method], p.reference, p.note, p.recorded_by_name && `recorded by ${p.recorded_by_name}`].filter(Boolean).join(" · ")}</span></div>
                    {can("payments.record") && <Button small variant="ghost" busy={busy === p.id} aria-label={`Remove the payment of ${naira2(p.amount_ngn)}`} onClick={() => {
                      if (window.confirm(`Remove this payment of ${naira2(p.amount_ngn)}? The invoice will be unpaid again.${inv.lines.some((l) => l.licence_applied_at) || inv.licence_applied_at ? " Licences already switched on stay on: change them in Geohub's staff console if needed." : ""}`))
                        void run(p.id, () => api.deletePayment(p.id), "Payment removed.").then((x) => x && setInv(x));
                    }}>Remove</Button>}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
        <section className="card pdf-card" aria-label="The invoice as the client sees it">
          {pdfUrl ? <iframe title={`${name} (PDF)`} src={pdfUrl} className="pdf" /> : <p className="loading">Making the PDF…</p>}
        </section>
      </div>
    </div>
  );
}

/** The licences an invoice pays for: one per product line (older invoices kept theirs on the invoice). */
export function licencesOf(inv: InvoiceDetail): Line[] {
  const on = inv.lines.filter((l) => l.licence_product && l.licence_plan);
  if (on.length || !inv.licence_plan) return on;
  return [{ description: "", quantity: "1", unit_price_ngn: "0", licence_product: inv.licence_product, licence_plan: inv.licence_plan,
    licence_starts: inv.licence_starts, licence_ends: inv.licence_ends, licence_applied_at: inv.licence_applied_at, licence_error: inv.licence_error }];
}

function Licence({ inv, org, onChange }: { inv: InvoiceDetail; org: GeohubOrg | null; onChange: (x: InvoiceDetail) => void }) {
  const { can } = useAuth();
  const { busy, run } = useAction();
  const lic = licencesOf(inv);
  const waiting = inv.status === "paid" && lic.some((l) => !l.licence_applied_at);
  return (
    <section className="card" aria-labelledby="lic-h">
      <h2 id="lic-h">{lic.length > 1 ? "Licences" : `${PRODUCT_NAME[lic[0].licence_product as Product]} licence`}</h2>
      <ul className="contacts">
        {lic.map((l) => (
          <li key={l.licence_product}>
            <div><strong>{licenceTitle(l.licence_product!, l.licence_plan!)}</strong>, {day(l.licence_starts!)} to {day(l.licence_ends!)}<br />
              {l.licence_applied_at ? <span className="ok-text small">Switched on in Geohub, {when(l.licence_applied_at)}.</span>
                : inv.status === "paid" ? <span className="error small">Not switched on yet. {l.licence_error}</span>
                : <span className="muted small">Switched on when this invoice is paid in full.</span>}
              {org && <NowOnGeohub org={org} product={l.licence_product!} />}</div>
          </li>
        ))}
      </ul>
      {inv.status !== "paid" && !inv.geohub_org_id && <p className="muted small">The client is not linked to Geohub yet.</p>}
      {waiting && <div className="actions">
        {inv.geohub_org_id && can("payments.record") && <Button small variant="primary" busy={busy === "retry"}
          onClick={() => void run("retry", () => api.retryLicence(inv.id, org?.status === "suspended"), "Done.").then((x) => x && onChange(x))}>
          Switch {lic.filter((l) => !l.licence_applied_at).length > 1 ? "them" : "it"} on now</Button>}
        {!inv.geohub_org_id && <Link className="btn btn-sm" to={`/clients/${inv.account_id}#geohub`}>Link or set up the client on Geohub</Link>}
      </div>}
    </section>
  );
}

function NowOnGeohub({ org, product }: { org: GeohubOrg; product: string }) {
  const p = product === "hub" ? { plan_name: org.plan_name, status_name: org.status_name, subscription_ends: org.subscription_ends }
    : org.products?.find((x) => x.product === product);
  return (
    <p className="muted small">{p ? <>Now: {p.plan_name}, {(p.status_name ?? "").toLowerCase()}{p.subscription_ends ? ` until ${day(p.subscription_ends)}` : ""}. </>
      : <>{org.name} does not have {PRODUCT_NAME[product]} yet. </>}
      <a href={org.console_url} target="_blank" rel="noreferrer">Open in Geohub</a></p>
  );
}

function IssueForm({ inv, onDone, onCancel }: { inv: InvoiceDetail; onDone: (x?: InvoiceDetail) => void; onCancel: () => void }) {
  const { busy, run } = useAction();
  const [on, setOn] = useState(isoToday());
  const [dueOn, setDueOn] = useState("");
  async function go(e: FormEvent) {
    e.preventDefault();
    onDone(await run("issue", () => api.issueInvoice(inv.id, { issue_date: on, due_date: dueOn || undefined }), "Issued."));
  }
  return (
    <form className="card row" onSubmit={go} aria-label="Issue the invoice">
      <p className="wide" style={{ flexBasis: "100%", margin: 0 }}>Issuing gives the invoice its number. After that it cannot change, only be voided.</p>
      <div className="field"><label htmlFor="is-on">Date</label><input id="is-on" type="date" required value={on} onChange={(e) => setOn(e.target.value)} /></div>
      <div className="field"><label htmlFor="is-due">Due (14 days if left empty)</label><input id="is-due" type="date" min={on} value={dueOn} onChange={(e) => setDueOn(e.target.value)} /></div>
      <div className="actions"><Button type="submit" variant="primary" busy={busy === "issue"}>Issue {naira2(inv.total_ngn)}</Button><Button variant="ghost" onClick={onCancel}>Cancel</Button></div>
    </form>
  );
}

function EmailForm({ inv, onDone, onCancel }: { inv: InvoiceDetail; onDone: (x?: InvoiceDetail) => void; onCancel: () => void }) {
  const { busy, run } = useAction();
  const [to, setTo] = useState(inv.bill_to.email ?? "");
  const [message, setMessage] = useState("");
  async function go(e: FormEvent) {
    e.preventDefault();
    onDone(await run("email", () => api.emailInvoice(inv.id, { to, message }), `Sent to ${to}.`));
  }
  return (
    <form className="card grid-form" onSubmit={go} aria-label="Email the invoice">
      <div className="field"><label htmlFor="em-to">To</label><input id="em-to" type="email" required value={to} onChange={(e) => setTo(e.target.value)} /></div>
      <div className="field wide"><label htmlFor="em-msg">A line of your own (optional)</label><textarea id="em-msg" rows={2} value={message} onChange={(e) => setMessage(e.target.value)} /></div>
      <p className="wide muted small">The email has the PDF attached, the amount and due date, and how to pay by transfer, signed with your name.</p>
      <div className="actions wide"><Button type="submit" variant="primary" busy={busy === "email"}>{inv.emailed_at ? "Send again" : "Send"}</Button><Button variant="ghost" onClick={onCancel}>Cancel</Button></div>
    </form>
  );
}

function PaymentForm({ inv, org, onDone, onCancel }: { inv: InvoiceDetail; org: GeohubOrg | null; onDone: (x?: InvoiceDetail) => void; onCancel: () => void }) {
  const { busy, run } = useAction();
  const [p, setP] = useState({ amount_ngn: String(Number(inv.balance_ngn)), paid_on: isoToday(), method: "bank_transfer", reference: "", note: "",
    lift_suspension: org?.status === "suspended" });
  const full = Number(p.amount_ngn) === Number(inv.balance_ngn);
  async function go(e: FormEvent) {
    e.preventDefault();
    onDone(await run("pay", () => api.addPayment(inv.id, p), full ? "Paid in full." : "Payment recorded."));
  }
  return (
    <form className="card grid-form" onSubmit={go} aria-label="Record a payment">
      <div className="field"><label htmlFor="pay-amount">Amount received (₦)</label><input id="pay-amount" type="number" min="0.01" step="0.01" max={Number(inv.balance_ngn)} required value={p.amount_ngn} onChange={(e) => setP({ ...p, amount_ngn: e.target.value })} /></div>
      <div className="field"><label htmlFor="pay-on">Date it reached the bank</label><input id="pay-on" type="date" required max={isoToday()} value={p.paid_on} onChange={(e) => setP({ ...p, paid_on: e.target.value })} /></div>
      <div className="field"><label htmlFor="pay-method">How</label>
        <select id="pay-method" value={p.method} onChange={(e) => setP({ ...p, method: e.target.value })}>{Object.entries(METHOD).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
      <div className="field"><label htmlFor="pay-ref">Bank reference</label><input id="pay-ref" value={p.reference} onChange={(e) => setP({ ...p, reference: e.target.value })} placeholder="From the bank alert" /></div>
      <div className="field wide"><label htmlFor="pay-note">Note (optional)</label><input id="pay-note" value={p.note} onChange={(e) => setP({ ...p, note: e.target.value })} /></div>
      {full && inv.licence_plan && <p className="wide small">{inv.geohub_org_id
        ? `Paying in full switches on ${licencesOf(inv).map((l) => `${licenceTitle(l.licence_product!, l.licence_plan!)} (${day(l.licence_starts!)} to ${day(l.licence_ends!)})`).join(", ")}.`
        : "Paying in full marks it paid. This client is not on Geohub yet: set it up from the client's page afterwards."}</p>}
      {full && org?.status === "suspended" && <label className="check wide"><input type="checkbox" checked={p.lift_suspension} onChange={(e) => setP({ ...p, lift_suspension: e.target.checked })} />
        Also lift the client's suspension on Geohub{org.suspended_reason ? ` (${org.suspended_reason})` : ""}</label>}
      <div className="actions wide"><Button type="submit" variant="primary" busy={busy === "pay"}>Record {naira2(p.amount_ngn || 0)}</Button><Button variant="ghost" onClick={onCancel}>Cancel</Button></div>
    </form>
  );
}

function VoidForm({ inv, onDone, onCancel }: { inv: InvoiceDetail; onDone: (x?: InvoiceDetail) => void; onCancel: () => void }) {
  const { busy, run } = useAction();
  const [reason, setReason] = useState("");
  return (
    <form className="card row" aria-label="Void the invoice" onSubmit={async (e) => { e.preventDefault(); onDone(await run("void", () => api.voidInvoice(inv.id, reason), `${inv.number} is void.`)); }}>
      <div className="field"><label htmlFor="void-why">Why is {inv.number} void?</label><input id="void-why" required maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Wrong client; replaced by a new invoice" /></div>
      <div className="actions"><Button type="submit" variant="danger" busy={busy === "void"}>Void it</Button><Button variant="ghost" onClick={onCancel}>Cancel</Button></div>
    </form>
  );
}
