CREATE OR REPLACE FUNCTION app.bump_listing_version_from_child()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
BEGIN
    -- A listing deletion cascades to its children; its parent row cannot be
    -- updated by a nested child-delete trigger.
    IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
        RETURN OLD;
    END IF;

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
