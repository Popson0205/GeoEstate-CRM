-- Invoices in naira with VAT, payments by bank transfer, the price list, and the link to Geohub.

-- What a year of each plan costs, before VAT. Super admins change it under Invoices -> Prices.
CREATE TABLE prices (
  plan text PRIMARY KEY CHECK (plan IN ('standard','advanced')),
  name text NOT NULL,
  amount_ngn numeric(14,2) NOT NULL CHECK (amount_ngn >= 0),
  updated_by uuid REFERENCES users ON DELETE SET NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO prices (plan, name, amount_ngn) VALUES
  ('standard', 'Organization Standard', 750000),
  ('advanced', 'Organization Advanced', 1500000);

-- A client's tax number (printed on its invoices) and where it came from on Geohub.
ALTER TABLE accounts ADD COLUMN tin text NOT NULL DEFAULT '';
ALTER TABLE accounts ADD COLUMN geohub_request_id uuid;
CREATE UNIQUE INDEX accounts_geohub_org_key ON accounts (geohub_org_id) WHERE geohub_org_id IS NOT NULL;
CREATE UNIQUE INDEX accounts_geohub_request_key ON accounts (geohub_request_id) WHERE geohub_request_id IS NOT NULL;

-- Invoice numbers run GE-<year>-0001, 0002 ... with no gaps: a number is given only when an invoice is issued.
CREATE TABLE invoice_counters (
  year int PRIMARY KEY,
  last int NOT NULL
);

CREATE TABLE invoices (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  number text UNIQUE,                                   -- null while a draft
  account_id uuid NOT NULL REFERENCES accounts ON DELETE RESTRICT,
  deal_id uuid REFERENCES deals ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','issued','paid','void')),
  issue_date date,
  due_date date,
  vat_rate numeric(5,2) NOT NULL DEFAULT 7.5,
  subtotal_ngn numeric(14,2) NOT NULL DEFAULT 0,
  vat_ngn numeric(14,2) NOT NULL DEFAULT 0,
  total_ngn numeric(14,2) NOT NULL DEFAULT 0,
  bill_to jsonb NOT NULL DEFAULT '{}',                  -- the client's name, address, contact and TIN when issued
  notes text NOT NULL DEFAULT '',
  -- the Geohub licence the invoice pays for, switched on when it is paid
  licence_plan text CHECK (licence_plan IN ('standard','advanced')),
  licence_starts date,
  licence_ends date,
  licence_applied_at timestamptz,
  licence_error text,
  emailed_at timestamptz,
  emailed_to text,
  issued_at timestamptz,
  issued_by uuid REFERENCES users ON DELETE SET NULL,
  paid_at timestamptz,
  voided_at timestamptz,
  void_reason text,
  created_by uuid REFERENCES users ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (licence_plan IS NULL OR (licence_starts IS NOT NULL AND licence_ends IS NOT NULL AND licence_ends >= licence_starts))
);
CREATE INDEX invoices_account_idx ON invoices (account_id, created_at DESC);
CREATE INDEX invoices_status_idx ON invoices (status, due_date);

CREATE TABLE invoice_lines (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id uuid NOT NULL REFERENCES invoices ON DELETE CASCADE,
  position int NOT NULL,
  description text NOT NULL,
  quantity numeric(12,2) NOT NULL CHECK (quantity > 0),
  unit_price_ngn numeric(14,2) NOT NULL CHECK (unit_price_ngn >= 0),
  amount_ngn numeric(14,2) NOT NULL
);
CREATE INDEX invoice_lines_invoice_idx ON invoice_lines (invoice_id, position);

-- Money received, recorded by staff when it reaches the bank.
CREATE TABLE payments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id uuid NOT NULL REFERENCES invoices ON DELETE RESTRICT,
  amount_ngn numeric(14,2) NOT NULL CHECK (amount_ngn > 0),
  paid_on date NOT NULL,
  method text NOT NULL DEFAULT 'bank_transfer' CHECK (method IN ('bank_transfer','cash','cheque','other')),
  reference text NOT NULL DEFAULT '',
  note text NOT NULL DEFAULT '',
  recorded_by uuid REFERENCES users ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX payments_invoice_idx ON payments (invoice_id);
