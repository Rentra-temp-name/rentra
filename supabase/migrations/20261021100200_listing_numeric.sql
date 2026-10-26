CREATE TABLE app.listing_numeric (
    listing_id uuid NOT NULL REFERENCES app.listings(id) ON DELETE CASCADE,
    field text NOT NULL REFERENCES app.numeric_fields(key) ON DELETE RESTRICT,
    value numeric NOT NULL,
    PRIMARY KEY (listing_id, field),
    CONSTRAINT listing_numeric_finite_non_rent_value_check
        CHECK (field <> 'rent_amount' AND value <> 'NaN'::numeric)
);

CREATE INDEX listing_numeric_field_idx ON app.listing_numeric (field);

ALTER TABLE app.listing_numeric ENABLE ROW LEVEL SECURITY;

CREATE POLICY listing_numeric_select_visible_or_owner ON app.listing_numeric
    FOR SELECT TO rentra_api
    USING (EXISTS (
        SELECT 1 FROM app.listings AS listing
        WHERE listing.id = listing_numeric.listing_id
          AND (
              listing.owner_id = nullif(current_setting('app.user_id', true), '')::uuid
              OR (listing.status = 'active' AND listing.suspended_at IS NULL)
          )
    ));

CREATE POLICY listing_numeric_insert_owner ON app.listing_numeric
    FOR INSERT TO rentra_api
    WITH CHECK (EXISTS (
        SELECT 1 FROM app.listings AS listing
        WHERE listing.id = listing_numeric.listing_id
          AND listing.owner_id = nullif(current_setting('app.user_id', true), '')::uuid
    ));

CREATE POLICY listing_numeric_update_owner ON app.listing_numeric
    FOR UPDATE TO rentra_api
    USING (EXISTS (
        SELECT 1 FROM app.listings AS listing
        WHERE listing.id = listing_numeric.listing_id
          AND listing.owner_id = nullif(current_setting('app.user_id', true), '')::uuid
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM app.listings AS listing
        WHERE listing.id = listing_numeric.listing_id
          AND listing.owner_id = nullif(current_setting('app.user_id', true), '')::uuid
    ));

CREATE POLICY listing_numeric_delete_owner ON app.listing_numeric
    FOR DELETE TO rentra_api
    USING (EXISTS (
        SELECT 1 FROM app.listings AS listing
        WHERE listing.id = listing_numeric.listing_id
          AND listing.owner_id = nullif(current_setting('app.user_id', true), '')::uuid
    ));

REVOKE ALL ON app.listing_numeric FROM PUBLIC, anon, authenticated, rentra_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON app.listing_numeric TO rentra_api;
