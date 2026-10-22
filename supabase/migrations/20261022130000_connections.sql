CREATE TABLE app.connections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES app.profiles(id) ON DELETE CASCADE,
    listing_id uuid NOT NULL REFERENCES app.listings(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT connections_user_listing_unique UNIQUE (user_id, listing_id)
);

CREATE INDEX connections_user_created_at_idx
    ON app.connections (user_id, created_at);
CREATE INDEX connections_listing_created_at_idx
    ON app.connections (listing_id, created_at);

ALTER TABLE app.connections ENABLE ROW LEVEL SECURITY;
CREATE POLICY connections_select_own ON app.connections
    FOR SELECT TO rentra_api
    USING (user_id = nullif(current_setting('app.user_id', true), '')::uuid);

REVOKE ALL ON app.connections FROM PUBLIC, anon, authenticated, rentra_api;
GRANT SELECT ON app.connections TO rentra_api;
