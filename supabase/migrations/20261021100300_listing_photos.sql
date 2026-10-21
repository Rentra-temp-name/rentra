CREATE TABLE app.listing_photos (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id uuid NOT NULL REFERENCES app.listings(id) ON DELETE CASCADE,
    storage_path text NOT NULL,
    position smallint NOT NULL CHECK (position BETWEEN 1 AND 10),
    CONSTRAINT listing_photos_listing_position_key UNIQUE (listing_id, position)
);

ALTER TABLE app.listing_photos ENABLE ROW LEVEL SECURITY;

CREATE POLICY listing_photos_select_visible_or_owner ON app.listing_photos
    FOR SELECT TO rentra_api
    USING (EXISTS (
        SELECT 1 FROM app.listings AS listing
        WHERE listing.id = listing_photos.listing_id
          AND (
              listing.owner_id = nullif(current_setting('app.user_id', true), '')::uuid
              OR (listing.status = 'active' AND listing.suspended_at IS NULL)
          )
    ));

CREATE POLICY listing_photos_insert_owner ON app.listing_photos
    FOR INSERT TO rentra_api
    WITH CHECK (EXISTS (
        SELECT 1 FROM app.listings AS listing
        WHERE listing.id = listing_photos.listing_id
          AND listing.owner_id = nullif(current_setting('app.user_id', true), '')::uuid
    ));

CREATE POLICY listing_photos_update_owner ON app.listing_photos
    FOR UPDATE TO rentra_api
    USING (EXISTS (
        SELECT 1 FROM app.listings AS listing
        WHERE listing.id = listing_photos.listing_id
          AND listing.owner_id = nullif(current_setting('app.user_id', true), '')::uuid
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM app.listings AS listing
        WHERE listing.id = listing_photos.listing_id
          AND listing.owner_id = nullif(current_setting('app.user_id', true), '')::uuid
    ));

CREATE POLICY listing_photos_delete_owner ON app.listing_photos
    FOR DELETE TO rentra_api
    USING (EXISTS (
        SELECT 1 FROM app.listings AS listing
        WHERE listing.id = listing_photos.listing_id
          AND listing.owner_id = nullif(current_setting('app.user_id', true), '')::uuid
    ));

REVOKE ALL ON app.listing_photos FROM PUBLIC, anon, authenticated, rentra_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON app.listing_photos TO rentra_api;
