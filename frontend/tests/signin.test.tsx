// Signing in for the first time: password, then setting up two-step sign-in, then the recovery codes. The server is faked.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { ToastProvider } from "../src/components/ui";
import { AuthProvider } from "../src/lib/auth";
import { LoginPage } from "../src/pages/AuthPages";

const user = { id: "u1", email: "boss@geoestate.example", name: "Idris Boss", role: "super_admin", role_name: "Super admin", perms: ["staff.manage"], mfa_enabled: true };
afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

function fakeServer(routes: Record<string, (body: any) => [number, unknown]>) {
  const calls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const path = url.replace(/^\/api/, "");
    calls.push(path);
    const [status, body] = routes[path]?.(init?.body ? JSON.parse(String(init.body)) : undefined) ?? [404, { detail: "Not found" }];
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  }));
  return calls;
}

const app = () => render(<MemoryRouter initialEntries={["/login"]}><AuthProvider><ToastProvider><Routes>
  <Route path="/login" element={<LoginPage />} /><Route path="/" element={<p>Home page</p>} />
</Routes></ToastProvider></AuthProvider></MemoryRouter>);

it("the first sign-in sets up two-step sign-in before anything opens", async () => {
  const calls = fakeServer({
    "/auth/login": (b) => (b.password === "a-long-password" ? [200, { next: "enroll", token: "t".repeat(30) }] : [401, { detail: "Wrong email or password." }]),
    "/auth/enroll/start": () => [200, { secret: "JBSWY3DPEHPK3PXP", otpauth_url: "otpauth://totp/GeoEstate%20CRM:boss?secret=JBSWY3DPEHPK3PXP" }],
    "/auth/enroll/finish": (b) => (b.code === "123456" ? [200, { access_token: "a", refresh_token: "r", expires_in: 1800, user,
      recovery_codes: Array.from({ length: 10 }, (_, i) => `code${i}-abcde`) }] : [422, { detail: "That code is not right." }]),
  });
  app();
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "boss@geoestate.example" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Wrong email or password.");
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "a-long-password" } });
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(await screen.findByRole("heading", { name: "Set up two-step sign-in" })).toBeTruthy();
  expect(await screen.findByRole("img", { name: /QR code/ })).toBeTruthy();
  expect(screen.getByText("JBSW Y3DP EHPK 3PXP")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Enter the 6-digit code the app shows"), { target: { value: "000000" } });
  fireEvent.click(screen.getByRole("button", { name: "Turn on and sign in" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/not right/);
  fireEvent.change(screen.getByLabelText("Enter the 6-digit code the app shows"), { target: { value: "123456" } });
  fireEvent.click(screen.getByRole("button", { name: "Turn on and sign in" }));
  expect(await screen.findByRole("heading", { name: "Save your recovery codes" })).toBeTruthy();
  expect(screen.getAllByRole("listitem")).toHaveLength(10);
  expect(screen.queryByText("Home page")).toBeNull();                    // not in until the codes are saved
  fireEvent.click(screen.getByRole("button", { name: /I have saved them/ }));
  await waitFor(() => expect(screen.getByText("Home page")).toBeTruthy());
  expect(localStorage.getItem("crm.access")).toBe("a");
  expect(calls).toEqual(["/auth/login", "/auth/login", "/auth/enroll/start", "/auth/enroll/finish", "/auth/enroll/finish"]);
});

it("later sign-ins ask for the app's code, or a recovery code", async () => {
  fakeServer({
    "/auth/login": () => [200, { next: "mfa", token: "t".repeat(30) }],
    "/auth/mfa": (b) => (b.code === "abcde-fghij" ? [200, { access_token: "a", refresh_token: "r", expires_in: 1800, user }] : [401, { detail: "That code is not right." }]),
  });
  app();
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "boss@geoestate.example" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "a-long-password" } });
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(await screen.findByRole("heading", { name: "Two-step sign-in" })).toBeTruthy();
  fireEvent.click(screen.getByRole("link", { name: /Use a recovery code/ }));
  fireEvent.change(screen.getByLabelText("Recovery code"), { target: { value: "abcde-fghij" } });
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  await waitFor(() => expect(screen.getByText("Home page")).toBeTruthy());
});
