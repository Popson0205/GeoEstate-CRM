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
  | Super admin | Everything, including staff and deleting clients or deals |
  | Account manager | Clients, contacts, deals and activity |
  | Support | Contacts and activity; sees everything else |
  | Finance | Activity and the activity log; sees everything else |

- **Clients:** companies, agencies and NGOs, as leads, customers or former customers, each with an account
  manager, contacts (one main contact), deals and activity. Search by name, city, contact or email.
- **Deals:** a board from New to Contacted, Demo, Proposal, then Won or Lost (a lost deal needs a reason). Amounts
  in naira, before VAT. Winning a deal makes its client a customer.
- **Tasks and activity:** tasks with a due date and who they are for; calls, meetings, emails and notes logged on
  a client or a deal. Home shows your next tasks, late ones, the pipeline and the latest activity.
- **Activity log** (super admins and finance): everything staff did, newest first.

## Deploying on Railway

1. In your Railway project, **New → GitHub Repo → GeoEstate-CRM**. Railway builds the `Dockerfile`.
2. **New → Database → PostgreSQL** in the same project.
3. In the CRM service's **Variables**:

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (a reference to the database) |
   | `JWT_SECRET` | a long random string (64 characters). Keep it: changing it signs everyone out and makes everyone set up two-step sign-in again |
   | `APP_URL` | the service's address, e.g. `https://geoestate-crm-production.up.railway.app` |
   | `SUPER_ADMIN_EMAIL` | `geoestate.ng@gmail.com` (the default) |
   | `SUPER_ADMIN_NAME` | the name to show for it |
   | `BREVO_API_KEY` | the same Brevo key as Geohub, to send emails |
   | `MAIL_FROM` | e.g. `GeoEstate CRM <no-reply@yourdomain>` (an address verified in Brevo) |

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
