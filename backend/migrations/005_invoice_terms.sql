-- The terms and conditions printed on every invoice, edited by super admins. An issued invoice keeps a copy of the
-- terms as they were when it was issued (invoices.terms), so later edits never change an invoice already sent;
-- invoices issued before this have none. A draft shows the current terms.
CREATE TABLE invoice_terms (
  id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  body text NOT NULL,
  updated_by uuid REFERENCES users ON DELETE SET NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO invoice_terms (body) VALUES (
'1. Validity. The prices on this invoice hold until {due_date}. After that date GeoEstate may reissue the invoice at its prices then current.
2. Payment. Payment is due in full by {due_date}, in Nigerian naira, by bank transfer to the account shown, with {number} as the reference. Bank charges are paid by the client. VAT is charged at the rate shown under the Value Added Tax Act.
3. Withholding tax. Where the client deducts withholding tax, it must send GeoEstate the receipt or credit note from the tax authority within 30 days; until then the amount deducted remains owed.
4. Licences. Each licence on this invoice is switched on when the invoice is paid in full and runs for the dates shown. It is a non-exclusive, non-transferable right for the client''s own organization to use the product, under GeoEstate''s terms of service.
5. Renewal. Licences do not renew by themselves. GeoEstate sends a renewal invoice before a licence ends; access may be limited or suspended if a licence ends unpaid.
6. Refunds. Licence fees are not refundable once the licence is switched on, except where the law requires. Training and other services may be moved to another date with at least 5 working days'' notice.
7. Data. The client''s data remains the client''s. GeoEstate processes it only to provide the service, in line with the Nigeria Data Protection Act 2023.
8. Queries. Any query about this invoice must reach {email} within 7 days of receipt. This invoice is governed by the laws of the Federal Republic of Nigeria.');

ALTER TABLE invoices ADD COLUMN terms text;
