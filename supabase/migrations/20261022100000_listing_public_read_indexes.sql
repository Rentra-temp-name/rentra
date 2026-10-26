-- Public listing feeds can order/filter by rent without indexing hidden rows.
CREATE INDEX listings_public_rent_amount_idx
    ON app.listings (rent_amount)
    WHERE status = 'active' AND suspended_at IS NULL;
