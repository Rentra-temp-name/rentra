CREATE TABLE app.notifications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES app.profiles(id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('property_connected', 'profile_connected')),
    listing_id uuid REFERENCES app.listings(id) ON DELETE SET NULL,
    other_user_id uuid REFERENCES app.profiles(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    read_at timestamptz
);

CREATE INDEX notifications_user_created_at_idx
    ON app.notifications (user_id, created_at DESC, id DESC);
CREATE INDEX notifications_listing_id_idx ON app.notifications (listing_id);
CREATE INDEX notifications_other_user_id_idx ON app.notifications (other_user_id);
CREATE INDEX notifications_unread_user_created_at_idx
    ON app.notifications (user_id, created_at DESC, id DESC)
    WHERE read_at IS NULL;

ALTER TABLE app.notifications ENABLE ROW LEVEL SECURITY;
CREATE POLICY notifications_select_own ON app.notifications
    FOR SELECT TO rentra_api
    USING (user_id = nullif(current_setting('app.user_id', true), '')::uuid);
CREATE POLICY notifications_update_own ON app.notifications
    FOR UPDATE TO rentra_api
    USING (user_id = nullif(current_setting('app.user_id', true), '')::uuid)
    WITH CHECK (user_id = nullif(current_setting('app.user_id', true), '')::uuid);

REVOKE ALL ON app.notifications FROM PUBLIC, anon, authenticated, rentra_api;
GRANT SELECT, UPDATE (read_at) ON app.notifications TO rentra_api;
