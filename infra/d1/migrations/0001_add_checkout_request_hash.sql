-- Apply only after inspecting the target schema. New databases already include this column.
-- Existing orders retain NULL and use the legacy replay comparison until migrated.
ALTER TABLE orders ADD COLUMN request_hash TEXT;
