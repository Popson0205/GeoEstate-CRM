import { describe as group, expect, it } from "vitest";
import { due, naira } from "../src/lib/format";
import { stageTotal } from "../src/pages/DealsPage";
import { describe } from "../src/pages/LogPage";
import type { AuditEntry, Deal } from "../src/lib/types";

group("formats", () => {
  it("shows naira without kobo, and a dash for no amount", () => {
    expect(naira("1500000.00")).toMatch(/1,500,000/);
    expect(naira("1500000.00")).toMatch(/₦|NGN/);
    expect(naira(null)).toBe("—");
  });
  it("says when a task is due, and when it is late", () => {
    const now = Date.parse("2026-11-03T10:00:00");
    expect(due(null, now)).toEqual({ text: "No due date", late: false });
    expect(due("2026-11-01T09:00:00", now)).toEqual({ text: "2 days late", late: true });
    expect(due("2026-11-04T09:00:00", now).text).toBe("Due tomorrow");
    expect(due("2026-11-03T18:00:00", now)).toEqual({ text: "Due today", late: false });
  });
  it("adds up a stage's deals, counting a missing amount as nothing", () => {
    const d = (stage: Deal["stage"], amount: string | null) => ({ stage, amount_ngn: amount }) as Deal;
    expect(stageTotal([d("proposal", "500000"), d("proposal", null), d("proposal", "250000.50"), d("won", "1")], "proposal")).toBe(750000.5);
  });
  it("tells the activity log in plain words", () => {
    const e = { action: "deal.move", details: { title: "Advanced", from: "proposal", to: "won" } } as unknown as AuditEntry;
    expect(describe(e)).toBe("moved a deal: Advanced, from proposal to won");
  });
});
