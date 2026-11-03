import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ActivityList } from "../components/Activities";
import { ErrorText } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { STAGE_LABEL, naira, plural } from "../lib/format";
import type { Home } from "../lib/types";

export default function HomePage() {
  const { user } = useAuth();
  const [h, setH] = useState<Home | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = () => void api.home().then(setH, setError);
  useEffect(load, []);
  if (error) return <div className="page"><ErrorText error={error} /></div>;
  if (!h) return <p className="loading">Loading…</p>;
  const open = h.pipeline.filter((p) => p.stage !== "won" && p.stage !== "lost");
  const openValue = open.reduce((s, p) => s + Number(p.value_ngn), 0);
  const max = Math.max(1, ...open.map((p) => p.count));
  return (
    <div className="page">
      <h1>Good {new Date().getHours() < 12 ? "morning" : new Date().getHours() < 17 ? "afternoon" : "evening"}, {user?.name.split(" ")[0]}</h1>
      <div className="tiles">
        <Link to="/tasks" className="tile"><span>Your open tasks</span><strong>{h.my_open_tasks}</strong>{h.my_overdue > 0 && <em className="late">{h.my_overdue} late</em>}</Link>
        <Link to="/deals" className="tile"><span>Open pipeline</span><strong>{naira(openValue)}</strong><em>{plural(open.reduce((s, p) => s + p.count, 0), "deal")}</em></Link>
        <div className="tile"><span>Won this month</span><strong>{naira(h.won_this_month_ngn)}</strong></div>
        <Link to="/clients" className="tile"><span>Customers</span><strong>{h.accounts.customer}</strong><em>{plural(h.accounts.lead, "lead")}</em></Link>
      </div>
      <div className="two">
        <section className="card">
          <h2>Pipeline</h2>
          <ul className="funnel">
            {open.map((p) => (
              <li key={p.stage}>
                <Link to={`/deals?stage=${p.stage}`}>{STAGE_LABEL[p.stage]}</Link>
                <span className="bar"><span style={{ width: `${(p.count / max) * 100}%` }} /></span>
                <span className="num">{p.count} · {naira(p.value_ngn)}</span>
              </li>
            ))}
          </ul>
        </section>
        <section className="card">
          <h2>Your next tasks</h2>
          <ActivityList items={h.my_tasks} onChange={load} />
          <p><Link to="/tasks">All tasks</Link></p>
        </section>
      </div>
      <section className="card">
        <h2>Latest activity</h2>
        <ActivityList items={h.recent} onChange={load} />
      </section>
    </div>
  );
}
