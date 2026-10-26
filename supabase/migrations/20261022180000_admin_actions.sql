CREATE TABLE app.admin_actions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_id uuid REFERENCES app.profiles(id) ON DELETE SET NULL,
    action text NOT NULL CHECK (action IN ('suspend', 'unsuspend', 'resolve_report')),
    listing_id uuid REFERENCES app.listings(id) ON DELETE SET NULL,
    reason text,
    at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX admin_actions_admin_id_idx ON app.admin_actions (admin_id);
CREATE INDEX admin_actions_listing_id_idx ON app.admin_actions (listing_id);

ALTER TABLE app.admin_actions ENABLE ROW LEVEL SECURITY;
CREATE POLICY admin_actions_select_own ON app.admin_actions
    FOR SELECT TO rentra_api
    USING (admin_id = nullif(current_setting('app.user_id', true), '')::uuid);
CREATE POLICY admin_actions_insert_admin ON app.admin_actions
    FOR INSERT TO rentra_api
    WITH CHECK (
        admin_id = nullif(current_setting('app.user_id', true), '')::uuid
        AND EXISTS (
            SELECT 1 FROM app.admins AS admin
            WHERE admin.user_id = nullif(current_setting('app.user_id', true), '')::uuid
        )
    );

REVOKE ALL ON app.admin_actions FROM PUBLIC, anon, authenticated, rentra_api;
GRANT SELECT, INSERT ON app.admin_actions TO rentra_api;
