CREATE TABLE app.listing_answers (
    listing_id uuid NOT NULL REFERENCES app.listings(id) ON DELETE CASCADE,
    attribute_id uuid NOT NULL REFERENCES app.attributes(id) ON DELETE RESTRICT,
    option_id uuid NOT NULL REFERENCES app.attribute_options(id) ON DELETE RESTRICT,
    PRIMARY KEY (listing_id, attribute_id, option_id)
);

CREATE INDEX listing_answers_attribute_option_listing_idx
    ON app.listing_answers (attribute_id, option_id, listing_id);
CREATE INDEX listing_answers_option_idx ON app.listing_answers (option_id);

ALTER TABLE app.listing_answers ENABLE ROW LEVEL SECURITY;

CREATE POLICY listing_answers_select_visible_or_owner ON app.listing_answers
    FOR SELECT TO rentra_api
    USING (EXISTS (
        SELECT 1
        FROM app.listings AS listing
        WHERE listing.id = listing_answers.listing_id
          AND (
              listing.owner_id = nullif(current_setting('app.user_id', true), '')::uuid
              OR (listing.status = 'active' AND listing.suspended_at IS NULL)
          )
    ));

CREATE POLICY listing_answers_insert_owner ON app.listing_answers
    FOR INSERT TO rentra_api
    WITH CHECK (EXISTS (
        SELECT 1 FROM app.listings AS listing
        WHERE listing.id = listing_answers.listing_id
          AND listing.owner_id = nullif(current_setting('app.user_id', true), '')::uuid
    ));

CREATE POLICY listing_answers_update_owner ON app.listing_answers
    FOR UPDATE TO rentra_api
    USING (EXISTS (
        SELECT 1 FROM app.listings AS listing
        WHERE listing.id = listing_answers.listing_id
          AND listing.owner_id = nullif(current_setting('app.user_id', true), '')::uuid
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM app.listings AS listing
        WHERE listing.id = listing_answers.listing_id
          AND listing.owner_id = nullif(current_setting('app.user_id', true), '')::uuid
    ));

CREATE POLICY listing_answers_delete_owner ON app.listing_answers
    FOR DELETE TO rentra_api
    USING (EXISTS (
        SELECT 1 FROM app.listings AS listing
        WHERE listing.id = listing_answers.listing_id
          AND listing.owner_id = nullif(current_setting('app.user_id', true), '')::uuid
    ));

REVOKE ALL ON app.listing_answers FROM PUBLIC, anon, authenticated, rentra_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON app.listing_answers TO rentra_api;
