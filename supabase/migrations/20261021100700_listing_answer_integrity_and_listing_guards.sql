-- Make each answer prove that its option belongs to the selected attribute.
ALTER TABLE app.attribute_options
    ADD CONSTRAINT attribute_options_attribute_id_id_key UNIQUE (attribute_id, id);

ALTER TABLE app.listing_answers
    ADD CONSTRAINT listing_answers_attribute_option_fk
    FOREIGN KEY (attribute_id, option_id)
    REFERENCES app.attribute_options (attribute_id, id)
    ON DELETE RESTRICT;

-- Multi-choice attributes may have several answers. Pick-one and yes/no
-- attributes may have only one answer for a listing. Serialize writes by the
-- listing/attribute pair so concurrent inserts cannot bypass this rule.
CREATE FUNCTION app.enforce_listing_answer_cardinality()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    attribute_type text;
    conflict_exists boolean;
BEGIN
    -- OLD's (listing_id, attribute_id) pair is not locked when either column
    -- is changed; the OLD row remains visible until this UPDATE commits.
    PERFORM pg_advisory_xact_lock(
        hashtextextended(NEW.listing_id::text || ':' || NEW.attribute_id::text, 0)
    );

    SELECT type INTO attribute_type
    FROM app.attributes
    WHERE id = NEW.attribute_id;

    IF attribute_type IN ('single', 'yes_no') THEN
        IF TG_OP = 'INSERT' THEN
            SELECT EXISTS (
                SELECT 1
                FROM app.listing_answers AS existing
                WHERE existing.listing_id = NEW.listing_id
                  AND existing.attribute_id = NEW.attribute_id
            ) INTO conflict_exists;
        ELSE
            SELECT EXISTS (
                SELECT 1
                FROM app.listing_answers AS existing
                WHERE existing.listing_id = NEW.listing_id
                  AND existing.attribute_id = NEW.attribute_id
                  AND (existing.listing_id, existing.attribute_id, existing.option_id)
                      IS DISTINCT FROM (OLD.listing_id, OLD.attribute_id, OLD.option_id)
            ) INTO conflict_exists;
        END IF;

        IF conflict_exists THEN
            RAISE EXCEPTION 'only one answer is allowed for this listing and attribute'
                USING ERRCODE = '23505',
                      CONSTRAINT = 'listing_answers_single_answer_per_listing_attribute_key';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION app.enforce_listing_answer_cardinality() FROM PUBLIC, anon, authenticated, rentra_api;

CREATE TRIGGER listing_answers_enforce_cardinality
BEFORE INSERT OR UPDATE ON app.listing_answers
FOR EACH ROW EXECUTE FUNCTION app.enforce_listing_answer_cardinality();

-- The API may edit listing content but lifecycle/security fields are controlled
-- by trusted database code, not direct UPDATE statements from rentra_api.
REVOKE UPDATE ON app.listings FROM rentra_api;
GRANT UPDATE (title, rent_amount, size_unit, point) ON app.listings TO rentra_api;

CREATE FUNCTION app.set_listing_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = app, pg_temp
AS $$
BEGIN
    NEW.updated_at := now();
    NEW.version := OLD.version + 1;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION app.set_listing_updated_at() FROM PUBLIC, anon, authenticated, rentra_api;

CREATE TRIGGER listings_set_updated_at
BEFORE UPDATE ON app.listings
FOR EACH ROW EXECUTE FUNCTION app.set_listing_updated_at();
