ALTER TABLE app.attributes ADD CONSTRAINT attributes_id_pick_rule_key UNIQUE (id, pick_rule);
CREATE TABLE app.requirements (
    user_id uuid NOT NULL REFERENCES app.profiles(id) ON DELETE CASCADE,
    attribute_id uuid NOT NULL REFERENCES app.attributes(id) ON DELETE RESTRICT,
    option_id uuid NOT NULL,
    pick_rule text NOT NULL CHECK (pick_rule IN ('yes_no', 'single', 'multi')),
    importance text NOT NULL CHECK (importance IN ('must', 'nice')),
    PRIMARY KEY (user_id, attribute_id, option_id),
    CONSTRAINT requirements_attribute_option_fk FOREIGN KEY (attribute_id, option_id)
      REFERENCES app.attribute_options(attribute_id, id) ON DELETE RESTRICT,
    CONSTRAINT requirements_attribute_rule_fk FOREIGN KEY (attribute_id, pick_rule)
      REFERENCES app.attributes(id, pick_rule) ON DELETE RESTRICT
);
CREATE INDEX requirements_option_idx ON app.requirements(attribute_id, option_id, user_id);
CREATE INDEX requirements_user_importance_idx ON app.requirements(user_id, importance);
CREATE UNIQUE INDEX requirements_single_must_idx ON app.requirements(user_id, attribute_id)
  WHERE importance = 'must' AND pick_rule = 'single';
ALTER TABLE app.requirements ENABLE ROW LEVEL SECURITY;
CREATE POLICY requirements_select_own ON app.requirements FOR SELECT TO rentra_api
  USING (user_id = nullif(current_setting('app.user_id', true), '')::uuid);
CREATE POLICY requirements_insert_own ON app.requirements FOR INSERT TO rentra_api
  WITH CHECK (user_id = nullif(current_setting('app.user_id', true), '')::uuid);
CREATE POLICY requirements_delete_own ON app.requirements FOR DELETE TO rentra_api
  USING (user_id = nullif(current_setting('app.user_id', true), '')::uuid);
REVOKE ALL ON app.requirements FROM PUBLIC, anon, authenticated, rentra_api;
GRANT SELECT, INSERT, DELETE ON app.requirements TO rentra_api;
