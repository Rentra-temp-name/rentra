CREATE FUNCTION app.bump_listing_version_from_child()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.listing_id IS DISTINCT FROM NEW.listing_id THEN
        UPDATE app.listings SET version = version + 1 WHERE id = OLD.listing_id;
        UPDATE app.listings SET version = version + 1 WHERE id = NEW.listing_id;
    ELSE
        UPDATE app.listings
        SET version = version + 1
        WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.listing_id ELSE NEW.listing_id END;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION app.bump_listing_version_from_child() FROM PUBLIC, anon, authenticated, rentra_api;

CREATE TRIGGER listing_answers_bump_listing_version
AFTER INSERT OR UPDATE OR DELETE ON app.listing_answers
FOR EACH ROW EXECUTE FUNCTION app.bump_listing_version_from_child();

CREATE TRIGGER listing_numeric_bump_listing_version
AFTER INSERT OR UPDATE OR DELETE ON app.listing_numeric
FOR EACH ROW EXECUTE FUNCTION app.bump_listing_version_from_child();

CREATE TRIGGER listing_photos_bump_listing_version
AFTER INSERT OR UPDATE OR DELETE ON app.listing_photos
FOR EACH ROW EXECUTE FUNCTION app.bump_listing_version_from_child();
