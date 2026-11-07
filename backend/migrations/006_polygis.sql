-- PolyGIS ('gis'), the web GIS, is sold and invoiced like the other products.
ALTER TABLE prices DROP CONSTRAINT IF EXISTS prices_product_check;
ALTER TABLE prices ADD CONSTRAINT prices_product_check CHECK (product IN ('hub','land','check','farm','gis'));
ALTER TABLE invoices DROP CONSTRAINT IF EXISTS invoices_licence_product_check;
ALTER TABLE invoices ADD CONSTRAINT invoices_licence_product_check CHECK (licence_product IN ('hub','land','check','farm','gis'));
ALTER TABLE invoice_lines DROP CONSTRAINT IF EXISTS invoice_lines_licence_product_check;
ALTER TABLE invoice_lines ADD CONSTRAINT invoice_lines_licence_product_check CHECK (licence_product IN ('hub','land','check','farm','gis'));
