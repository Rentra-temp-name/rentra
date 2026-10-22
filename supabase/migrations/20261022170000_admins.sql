CREATE TABLE app.admins (
    user_id uuid PRIMARY KEY REFERENCES app.profiles(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE app.admins ENABLE ROW LEVEL SECURITY;
CREATE POLICY admins_select_self ON app.admins
    FOR SELECT TO rentra_api
    USING (user_id = nullif(current_setting('app.user_id', true), '')::uuid);

REVOKE ALL ON app.admins FROM PUBLIC, anon, authenticated, rentra_api;
GRANT SELECT ON app.admins TO rentra_api;
