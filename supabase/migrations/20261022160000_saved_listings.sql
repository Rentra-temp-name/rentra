CREATE TABLE app.saved_listings (
    user_id uuid NOT NULL REFERENCES app.profiles(id) ON DELETE CASCADE,
    listing_id uuid NOT NULL REFERENCES app.listings(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, listing_id)
);

CREATE INDEX saved_listings_listing_id_idx ON app.saved_listings (listing_id);

ALTER TABLE app.saved_listings ENABLE ROW LEVEL SECURITY;
CREATE POLICY saved_listings_select_own ON app.saved_listings
    FOR SELECT TO rentra_api
    USING (user_id = nullif(current_setting('app.user_id', true), '')::uuid);
CREATE POLICY saved_listings_delete_own ON app.saved_listings
    FOR DELETE TO rentra_api
    USING (user_id = nullif(current_setting('app.user_id', true), '')::uuid);

REVOKE ALL ON app.saved_listings FROM PUBLIC, anon, authenticated, rentra_api;
GRANT SELECT, DELETE ON app.saved_listings TO rentra_api;
