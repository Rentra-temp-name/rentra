CREATE TABLE app.requirement_numeric (
    user_id uuid NOT NULL REFERENCES app.profiles(id) ON DELETE CASCADE,
    field text NOT NULL REFERENCES app.numeric_fields(key) ON DELETE RESTRICT,
    value numeric NOT NULL CHECK (value <> 'NaN'::numeric),
    importance text NOT NULL CHECK (importance IN ('must', 'nice')),
    PRIMARY KEY (user_id, field)
);
CREATE INDEX requirement_numeric_field_idx ON app.requirement_numeric(field, user_id);
ALTER TABLE app.requirement_numeric ENABLE ROW LEVEL SECURITY;
CREATE POLICY requirement_numeric_select_own ON app.requirement_numeric FOR SELECT TO rentra_api
  USING (user_id = nullif(current_setting('app.user_id', true), '')::uuid);
CREATE POLICY requirement_numeric_insert_own ON app.requirement_numeric FOR INSERT TO rentra_api
  WITH CHECK (user_id = nullif(current_setting('app.user_id', true), '')::uuid);
CREATE POLICY requirement_numeric_update_own ON app.requirement_numeric FOR UPDATE TO rentra_api
  USING (user_id = nullif(current_setting('app.user_id', true), '')::uuid)
  WITH CHECK (user_id = nullif(current_setting('app.user_id', true), '')::uuid);
CREATE POLICY requirement_numeric_delete_own ON app.requirement_numeric FOR DELETE TO rentra_api
  USING (user_id = nullif(current_setting('app.user_id', true), '')::uuid);
REVOKE ALL ON app.requirement_numeric FROM PUBLIC, anon, authenticated, rentra_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON app.requirement_numeric TO rentra_api;

DELETE FROM app.numeric_fields WHERE key IN ('size_unit');
UPDATE app.numeric_fields SET unit = 'sq ft' WHERE key = 'size_value';
