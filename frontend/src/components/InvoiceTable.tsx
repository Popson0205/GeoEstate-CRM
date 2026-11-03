import { Link } from "react-router-dom";
import { INVOICE_STATUS, PRODUCT_NAME, day, naira2 } from "../lib/format";
import type { Invoice } from "../lib/types";

export function InvoiceBadge({ i }: { i: Invoice }) {
  const label = i.overdue ? "Overdue" : i.status === "issued" && Number(i.paid_ngn) > 0 ? "Part paid" : INVOICE_STATUS[i.status];
  const tone = i.overdue ? "bad" : i.status === "paid" ? "ok" : i.status === "void" ? "off" : i.status === "issued" ? "warn" : "";
  return <span className={`badge ${tone}`}>{label}</span>;
}

/** Invoices as a table: number, client, dates, total, what is still owed. */
export default function InvoiceTable({ items, showClient = true }: { items: Invoice[]; showClient?: boolean }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead><tr>
          <th scope="col">Invoice</th>{showClient && <th scope="col">Client</th>}<th scope="col">Issued</th><th scope="col">Due</th>
          <th scope="col" className="r">Total</th><th scope="col" className="r">Owed</th><th scope="col">Status</th>
        </tr></thead>
        <tbody>
          {items.map((i) => (
            <tr key={i.id} className={i.status === "void" ? "is-off" : undefined}>
              <td><Link to={`/invoices/${i.id}`}><strong>{i.number ?? "Draft"}</strong></Link>
                {i.licence_plan && <><br /><span className="muted small">{PRODUCT_NAME[i.licence_product ?? "hub"]} licence</span></>}</td>
              {showClient && <td><Link to={`/clients/${i.account_id}`}>{i.account_name}</Link></td>}
              <td>{day(i.issue_date) || "—"}</td>
              <td className={i.overdue ? "late" : undefined}>{day(i.due_date) || "—"}</td>
              <td className="num r">{naira2(i.total_ngn)}</td>
              <td className="num r">{Number(i.balance_ngn) > 0 ? naira2(i.balance_ngn) : "—"}</td>
              <td><InvoiceBadge i={i} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
