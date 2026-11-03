# GeoEstate CRM

GeoEstate NIG Limited's back office: client accounts and their contacts, the sales pipeline, and staff tasks and
activity. Invoices, payments and the licensing link to Geohub come next. **Staff only:** nobody can sign up, and
everyone uses two-step sign-in.

## What it does

- **Sign-in:** email and password, then always a 6-digit code from an authenticator app (Google Authenticator,
  Microsoft Authenticator, 1Password…). The first time, each person sets the app up and saves ten recovery codes.
  No session is ever issued without the code.
- **Staff** (super admins): add people with a role; they are emailed a link to choose a password. Change roles,
  resend a link, reset two-step sign-in for a lost phone, or turn an account off (signed out at once, history kept).

  | Role | Can |
  | --- | --- |
  | Super admin | Everything, including staff, prices and deleting clients or deals |
  | Account manager | Clients, contacts, deals, activity and invoices; links clients to Geohub |
  | Support | Contacts and activity; sees everything else |
  | Finance | Invoices, payments, voiding, activity and the activity log; sees everything else |

- **Clients:** companies, agencies and NGOs, as leads, customers or former customers, each with an account
  manager, contacts (one main contact), deals and activity. Search by name, city, contact or email.
- **Deals:** a board from New to Contacted, Demo, Proposal, then Won or Lost (a lost deal needs a reason). Amounts
  in naira, before VAT. Winning a deal makes its client a customer.
- **Tasks and activity:** tasks with a due date and who they are for; calls, meetings, emails and notes logged on
  a client or a deal. Home shows your next tasks, late ones, the pipeline and the latest activity.
- **Invoices:** in naira with 7.5% VAT, numbered GE-2026-0001, GE-2026-0002 … with no gaps (a draft has no number;
  issuing gives it one). Each has a PDF with GeoEstate's logo, address, RC number and TIN, the client's details and
  TIN, the amount in words and the GTB account to pay into, and can be emailed to the client with the PDF attached.
  An issued invoice cannot change, only be voided (it keeps its number). The prices of Standard (₦750,000) and
  Advanced (₦1,500,000) a year, before VAT, are under **Invoices → Prices**.
- **Payments:** finance records each bank transfer with its reference. Paying in full marks the invoice paid, wins
  its deal and, if it is for a Geohub licence, **switches the licence on in Geohub** (the plan and dates on the
  invoice, as a paid licence, with the invoice number in Geohub's licence history). If Geohub cannot be reached, the
  payment is kept and the invoice offers to try again.
- **Geohub:** its customers and website requests, and which are in the CRM. Bring them in: a request becomes a lead
  with a deal and a task to contact them; a customer comes in linked to its organization. On a client's page: its
  licence on Geohub today, link or unlink it, or set it up on Geohub (from a paid invoice, or a month's demo).
- **Activity log** (super admins and finance): everything staff did, newest first.

## Deploying on Railway

1. In Geohub's Railway project, **New → GitHub Repo → GeoEstate-CRM**. Railway builds the `Dockerfile`.
2. No new database is needed: the CRM uses **Geohub's PostgreSQL**. It keeps all its tables in their own
   `crm` schema (created on first start), so they never mix with Geohub's tables, and Geohub never sees them.
3. In the CRM service's **Variables**:

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}`: the same database Geohub uses (pick it from the reference list) |
   | `DB_SCHEMA` | optional; `crm` by default |
   | `JWT_SECRET` | a long random string (64 characters). Keep it: changing it signs everyone out and makes everyone set up two-step sign-in again |
   | `APP_URL` | the service's address, e.g. `https://geoestate-crm-production.up.railway.app` |
   | `SUPER_ADMIN_EMAIL` | `geoestate.ng@gmail.com` (the default) |
   | `SUPER_ADMIN_NAME` | the name to show for it |
   | `BREVO_API_KEY` | the same Brevo key as Geohub, to send emails |
   | `MAIL_FROM` | e.g. `GeoEstate CRM <no-reply@yourdomain>` (an address verified in Brevo) |
   | `GEOHUB_URL` | Geohub's address, e.g. `https://triumphant-energy-production-72fe.up.railway.app` |
   | `GEOHUB_LINK_KEY` | a random string of 32+ characters; put **the same value** in Geohub's `CRM_LINK_KEY` |

   What invoices print (`COMPANY_NAME`, `COMPANY_ADDRESS`, `COMPANY_RC`, `COMPANY_TIN`, `COMPANY_EMAIL`,
   `COMPANY_PHONE`, `BANK_NAME`, `BANK_ACCOUNT_NAME`, `BANK_ACCOUNT_NUMBER`), `VAT_RATE` (7.5) and
   `INVOICE_DUE_DAYS` (14) are set already; add a variable only to change one.

4. **Settings → Networking → Generate Domain**, and put that address in `APP_URL`.
5. On the first start the CRM creates the super admin and emails it a link to choose a password. Without
   `BREVO_API_KEY` the link is written to the **Deploy Logs** instead (search for "set the password at"). Open
   it, choose a password, set up the authenticator app, save the recovery codes, then add your staff under
   **Staff**.

Lost the link? Use **Forgot your password?** on the sign-in page.

## Running it locally

```sh
# API on :8001 against a local PostgreSQL
cd backend && pip install -r requirements-dev.txt
DATABASE_URL=postgresql://user:pass@localhost:5432/crm JWT_SECRET=dev-secret-dev-secret-dev-secret APP_URL=http://localhost:5174 \
  uvicorn app.main:app --port 8001
# web app on :5174 (calls the API through /api)
cd frontend && npm install && npm run dev
```

## Running the tests

```sh
cd backend && cp .env.test.example .env.test && python -m pytest -q     # needs PostgreSQL with a crm_test database
cd frontend && npm test && npm run typecheck
```
