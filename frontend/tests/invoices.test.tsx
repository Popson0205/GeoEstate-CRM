// Making an invoice: the Geohub licence fills in its line from the price list and the client's licence dates; VAT is
// worked out as the server does. The server is faked.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe as group, expect, it, vi } from "vitest";
import { ToastProvider } from "../src/components/ui";
import { AuthProvider } from "../src/lib/auth";
import { invoiceTotals, nextStart, yearFrom } from "../src/lib/format";
import { describe } from "../src/pages/LogPage";
import InvoiceEditPage from "../src/pages/InvoiceEditPage";
import type { AuditEntry } from "../src/lib/types";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

group("invoice arithmetic", () => {
  it("adds VAT at 7.5% to the kobo, half up", () => {
    expect(invoiceTotals([{ quantity: "1", unit_price_ngn: "750000" }], 7.5)).toEqual({ amounts: [750000], subtotal: 750000, vat: 56250, total: 806250 });
    const t = invoiceTotals([{ quantity: "3", unit_price_ngn: "333.33" }, { quantity: "0.5", unit_price_ngn: "0.05" }], 7.5);
    expect(t.amounts).toEqual([999.99, 0.03]);
    expect(t.vat).toBe(75);
  });
  it("a year's licence, and when a renewal starts", () => {
    expect(yearFrom("2026-11-03")).toBe("2027-11-02");
    expect(yearFrom("2028-02-29")).toBe("2029-02-27");
    expect(nextStart("2027-01-31", "2026-11-03")).toBe("2027-02-01");
    expect(nextStart("2026-01-01", "2026-11-03")).toBe("2026-11-03");          // lapsed: from today
    expect(nextStart(null, "2026-11-03")).toBe("2026-11-03");
  });
  it("the activity log says what happened to the money", () => {
    const e = (action: string, details: Record<string, unknown>) => ({ id: 1, at: "", actor_id: null, actor_name: "Femi", action, target_type: null, target_id: null, details }) as AuditEntry;
    expect(describe(e("payment.record", { number: "GE-2026-0001", amount: "806250.00", reference: "GTB-1" }))).toMatch(/^recorded a payment on GE-2026-0001: .*806,250.*\(GTB-1\)$/);
    expect(describe(e("invoice.issue", { number: "GE-2026-0002", account: "Lagos Survey" }))).toBe("issued invoice GE-2026-0002: Lagos Survey");
    expect(describe(e("price.update", { plan: "standard", before: "750000.00", after: "800000.00" }))).toMatch(/standard: .*750,000.* to .*800,000/);
  });
});

it("one invoice for two products and training: each licence line fills in its price and dates from Geohub", async () => {
  const sent: any[] = [];
  const routes: Record<string, (b?: any) => unknown> = {
    "/me": () => ({ id: "u1", email: "f@geoestate.example", name: "Funke Ola", role: "account_manager", role_name: "Account manager", perms: ["invoices.edit"], mfa_enabled: true }),
    "/accounts": () => [{ id: "a1", name: "Kano Agency" }],
    "/prices": () => [{ product: "hub", plan: "standard", name: "Organization Standard", amount_ngn: "750000.00" }, { product: "hub", plan: "advanced", name: "Organization Advanced", amount_ngn: "1500000.00" },
      { product: "farm", plan: "standard", name: "FarmScan Standard", amount_ngn: "400000.00" }],
    "/company": () => ({ vat_rate: 7.5 }),
    "/accounts/a1": () => ({ id: "a1", name: "Kano Agency", geohub_org_id: "o1", email: "", deals: [{ id: "d1", title: "Renewal 2027" }],
      contacts: [{ id: "c1", name: "Ada Obi", email: "ada@kano.example" }], invoices: [] }),
    "/accounts/a1/geohub": () => ({ org: { plan_name: "Organization Standard", status_name: "Active", subscription_ends: "2027-01-31",
      products: [{ product: "farm", plan: "standard", plan_name: "FarmScan Standard", status: "active", status_name: "Active", subscription_ends: "2026-12-14" }] }, error: null }),
    "/invoices": (b) => { sent.push(b); return { id: "i1" }; },
  };
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const path = url.replace(/^\/api/, "").replace(/\?.*$/, "");
    const body = routes[path]?.(init?.body ? JSON.parse(String(init.body)) : undefined);
    return new Response(JSON.stringify(body ?? { detail: "Not found" }), { status: body ? 200 : 404, headers: { "Content-Type": "application/json" } });
  }));
  localStorage.setItem("crm.access", "token");
  render(<MemoryRouter initialEntries={["/invoices/new?client=a1"]}><AuthProvider><ToastProvider><Routes>
    <Route path="/invoices/new" element={<InvoiceEditPage />} /><Route path="/invoices/:id" element={<p>The invoice</p>} />
  </Routes></ToastProvider></AuthProvider></MemoryRouter>);

  const add = await screen.findByRole("button", { name: "+ Add a product" });
  await waitFor(() => expect((add as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(add);
  expect(await screen.findByText(/Now on Organization Standard \(active\) until 31 January 2027/)).toBeTruthy();
  expect((screen.getByLabelText("Product") as HTMLSelectElement).value).toBe("hub");
  const line = screen.getByLabelText("Line 1 description") as HTMLTextAreaElement;
  expect(line.value).toBe("Geohub Organization Standard licence, one year (1 February 2027 to 31 January 2028)");
  expect((screen.getByLabelText("Line 1 unit price") as HTMLInputElement).value).toBe("750000");
  expect((screen.getByLabelText("From") as HTMLInputElement).value).toBe("2027-02-01");
  const totals = screen.getByText("Total").closest("dl")!;
  expect(within(totals).getByText(/806,250\.00/)).toBeTruthy();

  // Advanced instead: the same line changes; a later start moves the end and the words
  fireEvent.change(screen.getByLabelText("Plan"), { target: { value: "advanced" } });
  expect((screen.getByLabelText("Line 1 unit price") as HTMLInputElement).value).toBe("1500000");
  fireEvent.change(screen.getByLabelText("From"), { target: { value: "2027-03-01" } });
  expect((screen.getByLabelText("To") as HTMLInputElement).value).toBe("2028-02-29");
  expect(line.value).toMatch(/Advanced licence, one year \(1 March 2027 to 29 February 2028\)/);

  // a second product on the same invoice: FarmScan, renewing after its own licence; Geohub's line stays as it was
  fireEvent.click(screen.getByRole("button", { name: "+ Add a product" }));
  const second = screen.getAllByLabelText("Product")[1] as HTMLSelectElement;
  expect([...second.options].map((o) => o.value)).not.toContain("hub");        // one licence per product
  fireEvent.change(second, { target: { value: "farm" } });
  expect(screen.getByText(/Now on FarmScan Standard \(active\) until 14 December 2026/)).toBeTruthy();
  expect((screen.getByLabelText("Line 2 description") as HTMLTextAreaElement).value).toBe("FarmScan Standard licence, one year (15 December 2026 to 14 December 2027)");
  expect((screen.getByLabelText("Line 2 unit price") as HTMLInputElement).value).toBe("400000");
  expect(line.value).toMatch(/^Geohub Organization Advanced licence/);
  // and training, typed in
  fireEvent.click(screen.getByRole("button", { name: "+ Add a line" }));
  fireEvent.change(screen.getByLabelText("Line 3 description"), { target: { value: "Training day" } });
  fireEvent.change(screen.getByLabelText("Line 3 unit price"), { target: { value: "50000" } });
  expect(within(totals).getByText(/2,096,250\.00/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Deal (optional)"), { target: { value: "d1" } });
  fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
  await waitFor(() => expect(screen.getByText("The invoice")).toBeTruthy());
  expect(sent[0]).toEqual({ account_id: "a1", deal_id: "d1", notes: "", lines: [
    { description: "Geohub Organization Advanced licence, one year (1 March 2027 to 29 February 2028)", quantity: "1", unit_price_ngn: "1500000",
      licence_product: "hub", licence_plan: "advanced", licence_starts: "2027-03-01", licence_ends: "2028-02-29" },
    { description: "FarmScan Standard licence, one year (15 December 2026 to 14 December 2027)", quantity: "1", unit_price_ngn: "400000",
      licence_product: "farm", licence_plan: "standard", licence_starts: "2026-12-15", licence_ends: "2027-12-14" },
    { description: "Training day", quantity: "1", unit_price_ngn: "50000", licence_product: null, licence_plan: null, licence_starts: null, licence_ends: null }] });
});

it("an invoice for another product prices and dates its own licence", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const path = url.replace(/^\/api/, "").replace(/\?.*$/, "");
    const routes: Record<string, unknown> = {
      "/me": { id: "u1", email: "f@g.example", name: "Funke Ola", role: "account_manager", role_name: "Account manager", perms: ["invoices.edit"], mfa_enabled: true },
      "/accounts": [{ id: "a1", name: "Kano Agency" }],
      "/prices": [{ product: "hub", plan: "standard", name: "Organization Standard", amount_ngn: "750000.00" }, { product: "farm", plan: "standard", name: "FarmScan Standard", amount_ngn: "400000.00" }],
      "/company": { vat_rate: 7.5 },
      "/accounts/a1": { id: "a1", name: "Kano Agency", geohub_org_id: "o1", email: "", deals: [], contacts: [], invoices: [] },
      "/accounts/a1/geohub": { org: { plan_name: "Organization Standard", status_name: "Active", subscription_ends: "2027-01-31",
        products: [{ product: "farm", plan: "standard", plan_name: "FarmScan Standard", status: "active", status_name: "Active", subscription_ends: "2026-12-14" }] }, error: null },
    };
    const body = routes[path];
    return new Response(JSON.stringify(body ?? { detail: "Not found" }), { status: body ? 200 : 404, headers: { "Content-Type": "application/json" } });
  }));
  localStorage.setItem("crm.access", "token");
  render(<MemoryRouter initialEntries={["/invoices/new?client=a1"]}><AuthProvider><ToastProvider><Routes>
    <Route path="/invoices/new" element={<InvoiceEditPage />} /></Routes></ToastProvider></AuthProvider></MemoryRouter>);
  const add = await screen.findByRole("button", { name: "+ Add a product" });
  await waitFor(() => expect((add as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(add);
  fireEvent.change(screen.getByLabelText("Product"), { target: { value: "farm" } });
  expect(await screen.findByText(/Now on FarmScan Standard \(active\) until 14 December 2026/)).toBeTruthy();
  expect((screen.getByLabelText("Line 1 description") as HTMLTextAreaElement).value).toBe("FarmScan Standard licence, one year (15 December 2026 to 14 December 2027)");
  expect((screen.getByLabelText("Line 1 unit price") as HTMLInputElement).value).toBe("400000");
  fireEvent.change(screen.getByLabelText("Plan"), { target: { value: "advanced" } });
  expect(screen.getByText(/No price is set for FarmScan Advanced/)).toBeTruthy();
  expect((screen.getByLabelText("Line 1 unit price") as HTMLInputElement).value).toBe("");
  fireEvent.change(screen.getByLabelText("Product"), { target: { value: "land" } });
  expect(await screen.findByText(/does not have Land Registry yet/)).toBeTruthy();
  expect((screen.getByLabelText("Line 1 description") as HTMLTextAreaElement).value).toMatch(/^Land Registry Advanced licence, one year/);
  // removing the product leaves an empty line to type into
  fireEvent.click(screen.getByRole("button", { name: "Remove Land Registry" }));
  expect(screen.getByText("No product on this invoice yet.")).toBeTruthy();
  expect((screen.getByLabelText("Line 1 description") as HTMLTextAreaElement).value).toBe("");
});
