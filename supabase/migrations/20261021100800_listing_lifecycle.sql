CREATE FUNCTION app.guard_listing_lifecycle()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    actor text;
    user_id uuid;
    internal_version_bump boolean := false;
BEGIN
    actor := nullif(current_setting('app.actor', true), '');
    BEGIN
        user_id := nullif(current_setting('app.user_id', true), '')::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
        user_id := NULL;
    END;

    IF TG_OP = 'INSERT' THEN
        IF actor IS DISTINCT FROM 'owner'
           OR user_id IS NULL
           OR NEW.owner_id IS DISTINCT FROM user_id
           OR NEW.status IS DISTINCT FROM 'draft'
           OR NEW.archived_from_status IS NOT NULL
           OR NEW.archived_at IS NOT NULL
           OR NEW.suspended_at IS NOT NULL
           OR NEW.suspended_by IS NOT NULL
           OR NEW.suspended_reason IS NOT NULL
           OR NEW.version IS DISTINCT FROM 1 THEN
            RAISE EXCEPTION 'LISTING_INSERT_REQUIRES_OWNER_DRAFT'
                USING ERRCODE = '23514', CONSTRAINT = 'listings_owner_draft_insert';
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        -- Account/profile deletion cascades are initiated by the trusted Auth
        -- deletion path, not by an owner request against an individual listing.
        IF pg_trigger_depth() > 1 THEN
            RETURN OLD;
        END IF;

        IF actor = 'owner' THEN
            IF OLD.owner_id IS DISTINCT FROM user_id THEN
                RAISE EXCEPTION 'LISTING_NOT_FOUND'
                    USING ERRCODE = 'P0002';
            END IF;
            IF OLD.suspended_at IS NOT NULL THEN
                RAISE EXCEPTION 'LISTING_SUSPENDED'
                    USING ERRCODE = '23514', CONSTRAINT = 'listings_suspended_owner_lock';
            END IF;
            IF OLD.status <> 'archived' THEN
                RAISE EXCEPTION 'LISTING_DELETE_REQUIRES_ARCHIVED'
                    USING ERRCODE = '23514', CONSTRAINT = 'listings_delete_archived_only';
            END IF;
            RETURN OLD;
        ELSIF actor = 'system' THEN
            IF OLD.suspended_at IS NOT NULL THEN
                RAISE EXCEPTION 'LISTING_SUSPENDED'
                    USING ERRCODE = '23514', CONSTRAINT = 'listings_suspended_system_lock';
            END IF;
            IF (OLD.status = 'archived'
                    AND OLD.archived_at < now() - interval '30 days')
               OR (OLD.status = 'draft'
                    AND OLD.updated_at < now() - interval '30 days') THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'LISTING_NOT_PURGEABLE'
                USING ERRCODE = '23514', CONSTRAINT = 'listings_system_purge_eligibility';
        ELSE
            RAISE EXCEPTION 'LISTING_ACTOR_REQUIRED'
                USING ERRCODE = '23514', CONSTRAINT = 'listings_lifecycle_actor';
        END IF;
    END IF;

    -- Child-table AFTER triggers update only version. Their nested parent
    -- update must pass this guard; set_listing_updated_at performs the single
    -- version increment for that write.
    internal_version_bump := pg_trigger_depth() > 1
        AND NEW.version = OLD.version + 1
        AND (to_jsonb(NEW) - 'version') = (to_jsonb(OLD) - 'version');
    IF internal_version_bump THEN
        RETURN NEW;
    END IF;

    IF actor IS NULL OR actor NOT IN ('owner', 'system', 'admin') THEN
        RAISE EXCEPTION 'LISTING_ACTOR_REQUIRED'
            USING ERRCODE = '23514', CONSTRAINT = 'listings_lifecycle_actor';
    END IF;

    IF actor = 'admin' THEN
        IF NEW.status IS DISTINCT FROM OLD.status
           OR (to_jsonb(NEW) - 'suspended_at' - 'suspended_by' - 'suspended_reason')
              IS DISTINCT FROM
              (to_jsonb(OLD) - 'suspended_at' - 'suspended_by' - 'suspended_reason') THEN
            RAISE EXCEPTION 'ADMIN_MAY_ONLY_CHANGE_SUSPENSION'
                USING ERRCODE = '23514', CONSTRAINT = 'listings_admin_suspension_only';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.owner_id IS DISTINCT FROM OLD.owner_id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR NEW.version IS DISTINCT FROM OLD.version
       OR NEW.status_changed_at IS DISTINCT FROM OLD.status_changed_at
       OR NEW.suspended_at IS DISTINCT FROM OLD.suspended_at
       OR NEW.suspended_by IS DISTINCT FROM OLD.suspended_by
       OR NEW.suspended_reason IS DISTINCT FROM OLD.suspended_reason
       OR NEW.updated_at IS DISTINCT FROM OLD.updated_at THEN
        RAISE EXCEPTION 'LISTING_LIFECYCLE_FIELDS_ARE_TRIGGER_CONTROLLED'
            USING ERRCODE = '23514', CONSTRAINT = 'listings_lifecycle_fields_protected';
    END IF;

    IF actor = 'owner' AND OLD.owner_id IS DISTINCT FROM user_id THEN
        RAISE EXCEPTION 'LISTING_NOT_FOUND'
            USING ERRCODE = 'P0002';
    END IF;

    IF NEW.status IS DISTINCT FROM OLD.status THEN
        IF NEW.archived_from_status IS DISTINCT FROM OLD.archived_from_status
           OR NEW.archived_at IS DISTINCT FROM OLD.archived_at THEN
            RAISE EXCEPTION 'LISTING_ARCHIVE_FIELDS_ARE_TRIGGER_CONTROLLED'
                USING ERRCODE = '23514', CONSTRAINT = 'listings_archive_fields_protected';
        END IF;

        IF actor = 'owner' THEN
            IF OLD.suspended_at IS NOT NULL THEN
                RAISE EXCEPTION 'LISTING_SUSPENDED'
                    USING ERRCODE = '23514', CONSTRAINT = 'listings_suspended_owner_lock';
            END IF;

            IF NEW.status = 'archived'
               AND OLD.status IN ('draft', 'active', 'rented', 'sold_out', 'unavailable') THEN
                NEW.archived_from_status := OLD.status;
                NEW.archived_at := now();
            ELSIF OLD.status = 'archived'
                  AND OLD.archived_from_status IS NOT NULL
                  AND NEW.status = OLD.archived_from_status THEN
                IF OLD.archived_at IS NULL
                   OR OLD.archived_at < now() - interval '30 days' THEN
                    RAISE EXCEPTION 'LISTING_RESTORE_WINDOW_EXPIRED'
                        USING ERRCODE = '23514', CONSTRAINT = 'listings_restore_before_purge';
                END IF;
                NEW.archived_from_status := NULL;
                NEW.archived_at := NULL;
            ELSIF OLD.status = 'draft' AND NEW.status = 'active' THEN
                NULL;
            ELSIF OLD.status = 'active'
                  AND NEW.status IN ('rented', 'sold_out', 'unavailable') THEN
                NULL;
            ELSIF OLD.status IN ('rented', 'sold_out', 'unavailable')
                  AND NEW.status = 'active' THEN
                NULL;
            ELSE
                RAISE EXCEPTION 'LISTING_INVALID_TRANSITION'
                    USING ERRCODE = '23514', CONSTRAINT = 'listings_allowed_transition';
            END IF;
        ELSIF actor = 'system' THEN
            IF OLD.suspended_at IS NOT NULL THEN
                RAISE EXCEPTION 'LISTING_SUSPENDED'
                    USING ERRCODE = '23514', CONSTRAINT = 'listings_suspended_system_lock';
            END IF;
            IF NEW.status <> 'archived'
               OR OLD.status NOT IN ('rented', 'sold_out', 'unavailable')
               OR OLD.status_changed_at >= now() - interval '30 days' THEN
                RAISE EXCEPTION 'LISTING_SYSTEM_ARCHIVE_NOT_DUE'
                    USING ERRCODE = '23514', CONSTRAINT = 'listings_system_archive_due';
            END IF;
            NEW.archived_from_status := OLD.status;
            NEW.archived_at := now();
        END IF;

        NEW.status_changed_at := now();
    ELSE
        IF NEW.archived_from_status IS DISTINCT FROM OLD.archived_from_status
           OR NEW.archived_at IS DISTINCT FROM OLD.archived_at THEN
            RAISE EXCEPTION 'LISTING_ARCHIVE_FIELDS_ARE_TRIGGER_CONTROLLED'
                USING ERRCODE = '23514', CONSTRAINT = 'listings_archive_fields_protected';
        END IF;

        IF actor = 'system' THEN
            RAISE EXCEPTION 'SYSTEM_MAY_ONLY_CHANGE_LISTING_STATUS_OR_PURGE'
                USING ERRCODE = '23514', CONSTRAINT = 'listings_system_update_scope';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION app.guard_listing_lifecycle() FROM PUBLIC, anon, authenticated, rentra_api;

CREATE TRIGGER listings_lifecycle_guard
BEFORE INSERT OR UPDATE OR DELETE ON app.listings
FOR EACH ROW EXECUTE FUNCTION app.guard_listing_lifecycle();

CREATE FUNCTION app.publish_listing(p_listing_id uuid)
RETURNS app.listings
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    user_id uuid;
    listing app.listings%ROWTYPE;
    missing_items text[] := ARRAY[]::text[];
    missing_attributes text[];
    missing_numeric text[];
BEGIN
    BEGIN
        user_id := nullif(current_setting('app.user_id', true), '')::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
        user_id := NULL;
    END;

    SELECT * INTO listing
    FROM app.listings
    WHERE id = p_listing_id AND owner_id = user_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'LISTING_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;

    PERFORM set_config('app.actor', 'owner', true);
    IF listing.status <> 'draft' THEN
        RAISE EXCEPTION 'LISTING_NOT_DRAFT' USING ERRCODE = '23514';
    END IF;
    IF listing.suspended_at IS NOT NULL THEN
        RAISE EXCEPTION 'LISTING_SUSPENDED' USING ERRCODE = '23514';
    END IF;

    IF listing.title IS NULL OR btrim(listing.title) = '' THEN
        missing_items := missing_items || ARRAY['title'];
    END IF;
    IF listing.rent_amount IS NULL OR listing.rent_amount <= 0 THEN
        missing_items := missing_items || ARRAY['rent_amount'];
    END IF;
    IF listing.point IS NULL THEN
        missing_items := missing_items || ARRAY['point'];
    END IF;

    SELECT COALESCE(array_agg('attribute:' || attribute.key ORDER BY attribute.key), ARRAY[]::text[])
    INTO missing_attributes
    FROM app.attributes AS attribute
    WHERE attribute.required_at_publish
      AND NOT EXISTS (
          SELECT 1 FROM app.listing_answers AS answer
          WHERE answer.listing_id = listing.id AND answer.attribute_id = attribute.id
      );
    missing_items := missing_items || missing_attributes;

    SELECT COALESCE(array_agg('numeric:' || required.field ORDER BY required.field), ARRAY[]::text[])
    INTO missing_numeric
    FROM unnest(ARRAY[
        'bedrooms', 'bathrooms_total', 'western_commodes', 'indian_squat_toilets',
        'kitchen_count', 'balconies', 'total_floors'
    ]::text[]) AS required(field)
    WHERE NOT EXISTS (
        SELECT 1 FROM app.listing_numeric AS numeric_value
        WHERE numeric_value.listing_id = listing.id
          AND numeric_value.field = required.field
    );
    missing_items := missing_items || missing_numeric;

    IF NOT EXISTS (
        SELECT 1 FROM app.profiles AS profile
        WHERE profile.id = user_id
          AND profile.whatsapp IS NOT NULL
          AND btrim(profile.whatsapp) <> ''
    ) THEN
        missing_items := missing_items || ARRAY['whatsapp'];
    END IF;

    IF cardinality(missing_items) > 0 THEN
        RAISE EXCEPTION 'LISTING_PUBLISH_INCOMPLETE'
            USING ERRCODE = 'P0001', DETAIL = array_to_string(missing_items, ',');
    END IF;

    UPDATE app.listings SET status = 'active'
    WHERE id = listing.id AND owner_id = user_id
    RETURNING * INTO listing;
    PERFORM set_config('app.actor', '', true);
    RETURN listing;
END;
$$;

CREATE FUNCTION app.set_listing_status(p_listing_id uuid, p_new_status text)
RETURNS app.listings
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    user_id uuid;
    listing app.listings%ROWTYPE;
BEGIN
    BEGIN
        user_id := nullif(current_setting('app.user_id', true), '')::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
        user_id := NULL;
    END;
    SELECT * INTO listing FROM app.listings
    WHERE id = p_listing_id AND owner_id = user_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'LISTING_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;
    PERFORM set_config('app.actor', 'owner', true);
    IF listing.status NOT IN ('active', 'rented', 'sold_out', 'unavailable')
       OR p_new_status NOT IN ('active', 'rented', 'sold_out', 'unavailable')
       OR p_new_status = listing.status THEN
        RAISE EXCEPTION 'LISTING_INVALID_TRANSITION'
            USING ERRCODE = '23514', CONSTRAINT = 'listings_allowed_transition';
    END IF;
    IF listing.suspended_at IS NOT NULL THEN
        RAISE EXCEPTION 'LISTING_SUSPENDED' USING ERRCODE = '23514';
    END IF;
    UPDATE app.listings SET status = p_new_status
    WHERE id = listing.id AND owner_id = user_id
    RETURNING * INTO listing;
    PERFORM set_config('app.actor', '', true);
    RETURN listing;
END;
$$;

CREATE FUNCTION app.archive_listing(p_listing_id uuid)
RETURNS app.listings
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    user_id uuid;
    listing app.listings%ROWTYPE;
BEGIN
    BEGIN
        user_id := nullif(current_setting('app.user_id', true), '')::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
        user_id := NULL;
    END;
    SELECT * INTO listing FROM app.listings
    WHERE id = p_listing_id AND owner_id = user_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'LISTING_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;
    PERFORM set_config('app.actor', 'owner', true);
    IF listing.suspended_at IS NOT NULL THEN
        RAISE EXCEPTION 'LISTING_SUSPENDED' USING ERRCODE = '23514';
    END IF;
    IF listing.status NOT IN ('draft', 'active', 'rented', 'sold_out', 'unavailable') THEN
        RAISE EXCEPTION 'LISTING_INVALID_TRANSITION'
            USING ERRCODE = '23514', CONSTRAINT = 'listings_allowed_transition';
    END IF;
    UPDATE app.listings SET status = 'archived'
    WHERE id = listing.id AND owner_id = user_id
    RETURNING * INTO listing;
    PERFORM set_config('app.actor', '', true);
    RETURN listing;
END;
$$;

CREATE FUNCTION app.restore_listing(p_listing_id uuid)
RETURNS app.listings
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    user_id uuid;
    listing app.listings%ROWTYPE;
BEGIN
    BEGIN
        user_id := nullif(current_setting('app.user_id', true), '')::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
        user_id := NULL;
    END;
    SELECT * INTO listing FROM app.listings
    WHERE id = p_listing_id AND owner_id = user_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'LISTING_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;
    PERFORM set_config('app.actor', 'owner', true);
    IF listing.suspended_at IS NOT NULL THEN
        RAISE EXCEPTION 'LISTING_SUSPENDED' USING ERRCODE = '23514';
    END IF;
    IF listing.status <> 'archived'
       OR listing.archived_from_status IS NULL
       OR listing.archived_at IS NULL
       OR listing.archived_at < now() - interval '30 days' THEN
        RAISE EXCEPTION 'LISTING_NOT_RESTORABLE'
            USING ERRCODE = '23514', CONSTRAINT = 'listings_restore_before_purge';
    END IF;
    UPDATE app.listings SET status = listing.archived_from_status
    WHERE id = listing.id AND owner_id = user_id
    RETURNING * INTO listing;
    PERFORM set_config('app.actor', '', true);
    RETURN listing;
END;
$$;

CREATE FUNCTION app.force_delete_listing(p_listing_id uuid)
RETURNS text[]
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    user_id uuid;
    listing app.listings%ROWTYPE;
    photo_paths text[];
    photo_path text;
BEGIN
    BEGIN
        user_id := nullif(current_setting('app.user_id', true), '')::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
        user_id := NULL;
    END;
    SELECT * INTO listing FROM app.listings
    WHERE id = p_listing_id AND owner_id = user_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'LISTING_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;
    PERFORM set_config('app.actor', 'owner', true);
    IF listing.suspended_at IS NOT NULL THEN
        RAISE EXCEPTION 'LISTING_SUSPENDED' USING ERRCODE = '23514';
    END IF;
    IF listing.status <> 'archived' THEN
        RAISE EXCEPTION 'LISTING_DELETE_REQUIRES_ARCHIVED'
            USING ERRCODE = '23514', CONSTRAINT = 'listings_delete_archived_only';
    END IF;

    SELECT COALESCE(array_agg(photo.storage_path ORDER BY photo.position, photo.id), ARRAY[]::text[])
    INTO photo_paths
    FROM app.listing_photos AS photo
    WHERE photo.listing_id = listing.id;

    IF to_regclass('app.storage_deletions') IS NOT NULL THEN
        FOREACH photo_path IN ARRAY photo_paths LOOP
            EXECUTE 'INSERT INTO app.storage_deletions (bucket, path) VALUES ($1, $2)'
                USING 'listing-photos', photo_path;
        END LOOP;
    END IF;

    DELETE FROM app.listings WHERE id = listing.id AND owner_id = user_id;
    PERFORM set_config('app.actor', '', true);
    RETURN photo_paths;
END;
$$;

REVOKE ALL ON FUNCTION app.publish_listing(uuid) FROM PUBLIC, anon, authenticated, rentra_api;
REVOKE ALL ON FUNCTION app.set_listing_status(uuid, text) FROM PUBLIC, anon, authenticated, rentra_api;
REVOKE ALL ON FUNCTION app.archive_listing(uuid) FROM PUBLIC, anon, authenticated, rentra_api;
REVOKE ALL ON FUNCTION app.restore_listing(uuid) FROM PUBLIC, anon, authenticated, rentra_api;
REVOKE ALL ON FUNCTION app.force_delete_listing(uuid) FROM PUBLIC, anon, authenticated, rentra_api;
REVOKE DELETE ON app.listings FROM rentra_api;

GRANT EXECUTE ON FUNCTION app.publish_listing(uuid) TO rentra_api;
GRANT EXECUTE ON FUNCTION app.set_listing_status(uuid, text) TO rentra_api;
GRANT EXECUTE ON FUNCTION app.archive_listing(uuid) TO rentra_api;
GRANT EXECUTE ON FUNCTION app.restore_listing(uuid) TO rentra_api;
GRANT EXECUTE ON FUNCTION app.force_delete_listing(uuid) TO rentra_api;
