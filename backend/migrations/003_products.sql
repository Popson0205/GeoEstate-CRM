-- Prices and invoices for every GeoEstate product: Geohub ('hub'), Land Registry ('land'), LandCheck ('check'),
-- FarmScan ('farm'). Existing prices and invoice licences are Geohub's.
ALTER TABLE prices ADD COLUMN product text NOT NULL DEFAULT 'hub' CHECK (product IN ('hub','land','check','farm'));
ALTER TABLE prices DROP CONSTRAINT prices_pkey;
ALTER TABLE prices ADD PRIMARY KEY (product, plan);
ALTER TABLE prices DROP CONSTRAINT IF EXISTS prices_plan_check;
ALTER TABLE prices ADD CONSTRAINT prices_plan_check CHECK (plan IN ('standard','advanced','custom'));

ALTER TABLE invoices ADD COLUMN licence_product text NOT NULL DEFAULT 'hub' CHECK (licence_product IN ('hub','land','check','farm'));
ALTER TABLE invoices DROP CONSTRAINT IF EXISTS invoices_licence_plan_check;
ALTER TABLE invoices ADD CONSTRAINT invoices_licence_plan_check CHECK (licence_plan IN ('standard','advanced','custom'));
