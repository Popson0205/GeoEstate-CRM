-- GeoEstate CRM: staff, client accounts and their contacts, deals, staff activities, and a log of what staff did.

-- ---------- staff ----------
CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL,
  name text NOT NULL,
  role text NOT NULL CHECK (role IN ('super_admin','account_manager','support','finance')),
  password_hash text,                         -- null until they choose one from their emailed link
  active boolean NOT NULL DEFAULT true,       -- a removed staff member keeps their history but cannot sign in
  totp_secret text,                           -- encrypted; two-step sign-in is required for everyone
  totp_enabled_at timestamptz,
  totp_last_step bigint,
  last_sign_in_at timestamptz,
  invited_by uuid REFERENCES users ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX users_email_key ON users (lower(email));

CREATE TABLE refresh_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users ON DELETE CASCADE,
  token_hash text NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX refresh_tokens_user_idx ON refresh_tokens (user_id);

CREATE TABLE password_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users ON DELETE CASCADE,
  token_hash text NOT NULL UNIQUE,
  purpose text NOT NULL CHECK (purpose IN ('set','reset')),
  expires_at timestamptz NOT NULL,
  used_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recovery_codes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users ON DELETE CASCADE,
  code_hash text NOT NULL,
  used_at timestamptz
);
CREATE INDEX recovery_codes_user_idx ON recovery_codes (user_id);

-- ---------- clients ----------
CREATE TABLE accounts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  industry text NOT NULL DEFAULT '',
  email text NOT NULL DEFAULT '',
  phone text NOT NULL DEFAULT '',
  website text NOT NULL DEFAULT '',
  address text NOT NULL DEFAULT '',
  city text NOT NULL DEFAULT '',
  state text NOT NULL DEFAULT '',
  country text NOT NULL DEFAULT 'Nigeria',
  status text NOT NULL DEFAULT 'lead' CHECK (status IN ('lead','customer','former')),
  owner_id uuid REFERENCES users ON DELETE SET NULL,     -- the account manager who looks after it
  geohub_org_id uuid,                                    -- its organization on Geohub, once it has one
  notes text NOT NULL DEFAULT '',
  created_by uuid REFERENCES users ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX accounts_name_idx ON accounts (lower(name));
CREATE INDEX accounts_owner_idx ON accounts (owner_id);

CREATE TABLE contacts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL REFERENCES accounts ON DELETE CASCADE,
  name text NOT NULL,
  title text NOT NULL DEFAULT '',
  email text NOT NULL DEFAULT '',
  phone text NOT NULL DEFAULT '',
  is_primary boolean NOT NULL DEFAULT false,
  notes text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX contacts_account_idx ON contacts (account_id);

CREATE TABLE deals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL REFERENCES accounts ON DELETE CASCADE,
  title text NOT NULL,
  plan text NOT NULL DEFAULT 'standard' CHECK (plan IN ('standard','advanced','custom','demo','other')),
  amount_ngn numeric(14,2),                              -- before VAT
  stage text NOT NULL DEFAULT 'new' CHECK (stage IN ('new','contacted','demo','proposal','won','lost')),
  owner_id uuid REFERENCES users ON DELETE SET NULL,
  expected_close date,
  lost_reason text NOT NULL DEFAULT '',
  notes text NOT NULL DEFAULT '',
  geohub_request_id uuid,                                -- the website request it came from
  closed_at timestamptz,
  created_by uuid REFERENCES users ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX deals_stage_idx ON deals (stage, updated_at DESC);
CREATE INDEX deals_account_idx ON deals (account_id);

-- Tasks, calls, meetings, emails and notes: what staff did or must do, on an account or a deal.
CREATE TABLE activities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind text NOT NULL CHECK (kind IN ('task','call','meeting','email','note')),
  subject text NOT NULL,
  body text NOT NULL DEFAULT '',
  due_at timestamptz,
  done_at timestamptz,
  owner_id uuid REFERENCES users ON DELETE SET NULL,     -- who it is assigned to
  account_id uuid REFERENCES accounts ON DELETE CASCADE,
  deal_id uuid REFERENCES deals ON DELETE CASCADE,
  created_by uuid REFERENCES users ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX activities_owner_idx ON activities (owner_id, done_at, due_at);
CREATE INDEX activities_account_idx ON activities (account_id, created_at DESC);
CREATE INDEX activities_deal_idx ON activities (deal_id, created_at DESC);

-- ---------- what staff did ----------
CREATE TABLE audit_log (
  id bigserial PRIMARY KEY,
  at timestamptz NOT NULL DEFAULT now(),
  actor_id uuid REFERENCES users ON DELETE SET NULL,
  action text NOT NULL,
  target_type text,
  target_id text,
  details jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX audit_log_at_idx ON audit_log (id DESC);
