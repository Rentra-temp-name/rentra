-- Private application profiles. Public contact fields are served deliberately by
-- public profile/listing endpoints; table access remains owner-scoped.
CREATE TABLE app.profiles (
    id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name text,
    whatsapp text,
    deletion_requested_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT profiles_whatsapp_nepal_e164_check
        CHECK (whatsapp IS NULL OR whatsapp ~ '^\+977[1-9][0-9]{7,9}$')
);

ALTER TABLE app.profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY profiles_select_own ON app.profiles
    FOR SELECT
    USING (id = nullif(current_setting('app.user_id', true), '')::uuid);

CREATE POLICY profiles_insert_own ON app.profiles
    FOR INSERT
    WITH CHECK (id = nullif(current_setting('app.user_id', true), '')::uuid);

CREATE POLICY profiles_update_own ON app.profiles
    FOR UPDATE
    USING (id = nullif(current_setting('app.user_id', true), '')::uuid)
    WITH CHECK (id = nullif(current_setting('app.user_id', true), '')::uuid);

REVOKE ALL ON app.profiles FROM PUBLIC, anon, authenticated, rentra_api;
GRANT SELECT, INSERT, UPDATE ON app.profiles TO rentra_api;
