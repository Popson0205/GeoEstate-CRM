import { useEffect, useState } from "react";
import { ActivityList, AddActivity } from "../components/Activities";
import { ErrorText } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { Activity, StaffBrief } from "../lib/types";

type Who = "mine" | "all" | string;

export default function TasksPage() {
  const { can } = useAuth();
  const [who, setWho] = useState<Who>("mine");
  const [status, setStatus] = useState<"open" | "done">("open");
  const [due, setDue] = useState<"" | "overdue" | "today" | "week">("");
  const [items, setItems] = useState<Activity[] | null>(null);
  const [staff, setStaff] = useState<StaffBrief[]>([]);
  const [error, setError] = useState<unknown>(null);

  const load = () => void api.activities({ mine: who === "mine" || undefined, owner_id: who !== "mine" && who !== "all" ? who : undefined,
    status, due: due || undefined, kind: status === "open" ? "task" : undefined }).then(setItems, setError);
  useEffect(load, [who, status, due]);
  useEffect(() => { void api.staffBrief().then(setStaff, () => setStaff([])); }, []);

  return (
    <div className="page">
      <h1>Tasks</h1>
      {can("activities.edit") && <section className="card"><h2>Add a task</h2><AddActivity staff={staff} onAdded={load} /></section>}
      <div className="toolbar">
        <div className="field inline"><label htmlFor="t-who">For</label>
          <select id="t-who" value={who} onChange={(e) => setWho(e.target.value)}>
            <option value="mine">Me</option><option value="all">Everyone</option>
            {staff.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select></div>
        <div className="chips" role="group" aria-label="Show">
          <button type="button" className={`chip${status === "open" ? " is-on" : ""}`} aria-pressed={status === "open"} onClick={() => setStatus("open")}>To do</button>
          <button type="button" className={`chip${status === "done" ? " is-on" : ""}`} aria-pressed={status === "done"} onClick={() => { setStatus("done"); setDue(""); }}>Done and logged</button>
        </div>
        {status === "open" && (
          <div className="chips" role="group" aria-label="Due">
            {([["", "Any time"], ["overdue", "Late"], ["today", "Due today"], ["week", "This week"]] as const).map(([v, l]) => (
              <button key={v} type="button" className={`chip${due === v ? " is-on" : ""}`} aria-pressed={due === v} onClick={() => setDue(v)}>{l}</button>
            ))}
          </div>
        )}
      </div>
      <ErrorText error={error} />
      {items ? <ActivityList items={items} onChange={load} /> : <p className="loading">Loading…</p>}
    </div>
  );
}
