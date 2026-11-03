import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button, ErrorText, useAction } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { PLAN_LABEL, STAGES, STAGE_LABEL, day, naira } from "../lib/format";
import type { Account, Deal, Plan, Stage, StaffBrief } from "../lib/types";

/** The total of a stage's deals, in naira (deals without an amount count as nothing). */
export const stageTotal = (deals: Deal[], stage: Stage) => deals.filter((d) => d.stage === stage).reduce((s, d) => s + Number(d.amount_ngn ?? 0), 0);

/** A new deal, on a given client or one chosen here. */
export function DealForm({ staff, accountId, onDone }: { staff: StaffBrief[]; accountId?: string; onDone: (saved: boolean) => void }) {
  const { user } = useAuth();
  const { busy, run } = useAction();
  const [clients, setClients] = useState<Account[]>([]);
  const [f, setF] = useState({ account_id: accountId ?? "", title: "", plan: "standard" as Plan, amount: "", expected_close: "", owner_id: user?.id ?? "" });
  useEffect(() => { if (!accountId) void api.accounts().then(setClients, () => setClients([])); }, [accountId]);
  async function submit(e: FormEvent) {
    e.preventDefault();
    const d = await run("deal", () => api.createDeal({ account_id: f.account_id, title: f.title.trim(), plan: f.plan, amount_ngn: f.amount ? f.amount : null,
      expected_close: f.expected_close || null, owner_id: f.owner_id || null }), "Deal added.");
    if (d) onDone(true);
  }
  return (
    <form className="card grid-form" onSubmit={submit} aria-label="New deal">
      {!accountId && (
        <div className="field wide"><label htmlFor="d-client">Client</label>
          <select id="d-client" required value={f.account_id} onChange={(e) => setF({ ...f, account_id: e.target.value })}>
            <option value="">Choose a client…</option>{clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          {clients.length === 0 && <span className="muted small">Add the client first, under Clients.</span>}</div>
      )}
      <div className="field wide"><label htmlFor="d-title">Deal</label><input id="d-title" required maxLength={200} placeholder="e.g. Organization Standard, first year" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></div>
      <div className="field"><label htmlFor="d-plan">Plan</label>
        <select id="d-plan" value={f.plan} onChange={(e) => setF({ ...f, plan: e.target.value as Plan })}>
          {(Object.keys(PLAN_LABEL) as Plan[]).map((p) => <option key={p} value={p}>{PLAN_LABEL[p]}</option>)}
        </select></div>
      <div className="field"><label htmlFor="d-amount">Amount in naira, before VAT</label><input id="d-amount" type="number" min={0} step="0.01" inputMode="decimal" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></div>
      <div className="field"><label htmlFor="d-close">Expected to close</label><input id="d-close" type="date" value={f.expected_close} onChange={(e) => setF({ ...f, expected_close: e.target.value })} /></div>
      <div className="field"><label htmlFor="d-owner">Owner</label>
        <select id="d-owner" value={f.owner_id} onChange={(e) => setF({ ...f, owner_id: e.target.value })}>{staff.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
      <div className="actions wide"><Button type="submit" variant="primary" busy={busy === "deal"}>Add deal</Button><Button variant="ghost" onClick={() => onDone(false)}>Cancel</Button></div>
    </form>
  );
}

export default function DealsPage() {
  const { can } = useAuth();
  const { busy, run } = useAction();
  const [params] = useSearchParams();
  const [deals, setDeals] = useState<Deal[] | null>(null);
  const [staff, setStaff] = useState<StaffBrief[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [adding, setAdding] = useState(false);
  const [mine, setMine] = useState(false);
  const { user } = useAuth();
  const focus = params.get("focus");

  const load = () => void api.deals().then(setDeals, setError);
  useEffect(() => { load(); void api.staffBrief().then(setStaff, () => setStaff([])); }, []);

  async function move(d: Deal, stage: Stage) {
    let lost_reason: string | undefined;
    if (stage === "lost") {
      const why = window.prompt(`Why was "${d.title}" lost?`, d.lost_reason || "");
      if (!why?.trim()) return;
      lost_reason = why.trim();
    }
    if (await run(d.id, () => api.updateDeal(d.id, { stage, lost_reason }), `${d.title}: ${STAGE_LABEL[stage]}.`)) load();
  }

  if (error) return <div className="page"><ErrorText error={error} /></div>;
  if (!deals) return <p className="loading">Loading…</p>;
  const shown = mine ? deals.filter((d) => d.owner_id === user?.id) : deals;
  return (
    <div className="page page-wide">
      <div className="head">
        <h1>Deals</h1>
        <div className="actions">
          <label className="check"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />Only mine</label>
          {can("deals.edit") && !adding && <Button variant="primary" onClick={() => setAdding(true)}>Add a deal</Button>}
        </div>
      </div>
      {adding && <DealForm staff={staff} onDone={(saved) => { setAdding(false); if (saved) load(); }} />}
      <p className="muted small">Won and lost deals from the last 90 days. Amounts are before VAT.</p>
      <div className="board">
        {STAGES.map((s) => {
          const col = shown.filter((d) => d.stage === s.id);
          return (
            <section key={s.id} className={`col col-${s.id}`} aria-label={s.label}>
              <h2>{s.label} <span className="muted">{col.length}</span></h2>
              <p className="col-total">{naira(stageTotal(shown, s.id))}</p>
              {col.map((d) => (
                <article key={d.id} className={`deal${focus === d.id ? " is-focus" : ""}`}>
                  <strong>{d.title}</strong>
                  <Link to={`/clients/${d.account_id}`} className="small">{d.account_name}</Link>
                  <span className="small">{naira(d.amount_ngn)}{d.expected_close && s.id !== "won" && s.id !== "lost" ? ` · by ${day(d.expected_close)}` : ""}</span>
                  {d.stage === "lost" && d.lost_reason && <span className="muted small">{d.lost_reason}</span>}
                  <span className="muted small">{d.owner_name ?? "No owner"}</span>
                  {can("deals.edit") && (
                    <select aria-label={`Move ${d.title}`} value={d.stage} disabled={busy === d.id} onChange={(e) => void move(d, e.target.value as Stage)}>
                      {STAGES.map((x) => <option key={x.id} value={x.id}>{x.id === d.stage ? `In ${x.label}` : `Move to ${x.label}`}</option>)}
                    </select>
                  )}
                </article>
              ))}
            </section>
          );
        })}
      </div>
    </div>
  );
}
