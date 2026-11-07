-- Several products on one invoice: each line can carry the licence it pays for (Geohub, Land Registry, LandCheck,
-- FarmScan; at most one line per product), switched on when the invoice is paid. Lines without one are services
-- such as training. The invoice's own licence_* columns stay as a summary (the Geohub line first, else the first).
ALTER TABLE invoice_lines
  ADD COLUMN licence_product text CHECK (licence_product IN ('hub','land','check','farm')),
  ADD COLUMN licence_plan text CHECK (licence_plan IN ('standard','advanced','custom')),
  ADD COLUMN licence_starts date,
  ADD COLUMN licence_ends date,
  ADD COLUMN licence_applied_at timestamptz,
  ADD COLUMN licence_error text,
  ADD CONSTRAINT invoice_lines_licence_check CHECK (
    (licence_product IS NULL AND licence_plan IS NULL AND licence_starts IS NULL AND licence_ends IS NULL) OR
    (licence_product IS NOT NULL AND licence_plan IS NOT NULL AND licence_starts IS NOT NULL AND licence_ends IS NOT NULL
     AND licence_ends >= licence_starts));
CREATE UNIQUE INDEX invoice_lines_one_per_product ON invoice_lines (invoice_id, licence_product) WHERE licence_product IS NOT NULL;

-- an invoice's licence was its first line
UPDATE invoice_lines l SET licence_product = i.licence_product, licence_plan = i.licence_plan, licence_starts = i.licence_starts,
       licence_ends = i.licence_ends, licence_applied_at = i.licence_applied_at, licence_error = i.licence_error
FROM invoices i WHERE l.invoice_id = i.id AND l.position = 0 AND i.licence_plan IS NOT NULL;
