-- The API role has no direct DELETE grant on listings. This dedicated actor is
-- therefore usable only by the SECURITY DEFINER account-deletion path below.
CREATE OR REPLACE FUNCTION app.guard_listing_lifecycle()
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
        IF actor IS DISTINCT FROM 'owner' OR user_id IS NULL
           OR NEW.owner_id IS DISTINCT FROM user_id OR NEW.status IS DISTINCT FROM 'draft'
           OR NEW.archived_from_status IS NOT NULL OR NEW.archived_at IS NOT NULL
           OR NEW.suspended_at IS NOT NULL OR NEW.suspended_by IS NOT NULL
           OR NEW.suspended_reason IS NOT NULL OR NEW.version IS DISTINCT FROM 1 THEN
            RAISE EXCEPTION 'LISTING_INSERT_REQUIRES_OWNER_DRAFT'
                USING ERRCODE = '23514', CONSTRAINT = 'listings_owner_draft_insert';
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        IF pg_trigger_depth() > 1 THEN RETURN OLD; END IF;
        IF actor = 'owner' THEN
            IF OLD.owner_id IS DISTINCT FROM user_id THEN
                RAISE EXCEPTION 'LISTING_NOT_FOUND' USING ERRCODE = 'P0002';
            END IF;
            IF OLD.suspended_at IS NOT NULL THEN
                RAISE EXCEPTION 'LISTING_SUSPENDED' USING ERRCODE = '23514', CONSTRAINT = 'listings_suspended_owner_lock';
            END IF;
            IF OLD.status <> 'archived' THEN
                RAISE EXCEPTION 'LISTING_DELETE_REQUIRES_ARCHIVED'
                    USING ERRCODE = '23514', CONSTRAINT = 'listings_delete_archived_only';
            END IF;
            RETURN OLD;
        ELSIF actor = 'system' THEN
            IF OLD.suspended_at IS NOT NULL THEN
                RAISE EXCEPTION 'LISTING_SUSPENDED' USING ERRCODE = '23514', CONSTRAINT = 'listings_suspended_system_lock';
            END IF;
            IF (OLD.status = 'archived' AND OLD.archived_at < now() - interval '30 days')
               OR (OLD.status = 'draft' AND OLD.updated_at < now() - interval '30 days') THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'LISTING_NOT_PURGEABLE'
                USING ERRCODE = '23514', CONSTRAINT = 'listings_system_purge_eligibility';
        ELSIF actor = 'account_deletion' THEN
            IF user_id IS NULL OR OLD.owner_id IS DISTINCT FROM user_id THEN
                RAISE EXCEPTION 'LISTING_NOT_FOUND' USING ERRCODE = 'P0002';
            END IF;
            RETURN OLD;
        ELSE
            RAISE EXCEPTION 'LISTING_ACTOR_REQUIRED'
                USING ERRCODE = '23514', CONSTRAINT = 'listings_lifecycle_actor';
        END IF;
    END IF;

    internal_version_bump := pg_trigger_depth() > 1
        AND NEW.version = OLD.version + 1
        AND (to_jsonb(NEW) - 'version') = (to_jsonb(OLD) - 'version');
    IF internal_version_bump THEN RETURN NEW; END IF;

    IF actor IS NULL OR actor NOT IN ('owner', 'system', 'admin') THEN
        RAISE EXCEPTION 'LISTING_ACTOR_REQUIRED'
            USING ERRCODE = '23514', CONSTRAINT = 'listings_lifecycle_actor';
    END IF;
    IF actor = 'admin' THEN
        IF NEW.status IS DISTINCT FROM OLD.status
           OR (to_jsonb(NEW) - 'suspended_at' - 'suspended_by' - 'suspended_reason')
              IS DISTINCT FROM (to_jsonb(OLD) - 'suspended_at' - 'suspended_by' - 'suspended_reason') THEN
            RAISE EXCEPTION 'ADMIN_MAY_ONLY_CHANGE_SUSPENSION'
                USING ERRCODE = '23514', CONSTRAINT = 'listings_admin_suspension_only';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.owner_id IS DISTINCT FROM OLD.owner_id OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR NEW.version IS DISTINCT FROM OLD.version OR NEW.status_changed_at IS DISTINCT FROM OLD.status_changed_at
       OR NEW.suspended_at IS DISTINCT FROM OLD.suspended_at OR NEW.suspended_by IS DISTINCT FROM OLD.suspended_by
       OR NEW.suspended_reason IS DISTINCT FROM OLD.suspended_reason OR NEW.updated_at IS DISTINCT FROM OLD.updated_at THEN
        RAISE EXCEPTION 'LISTING_LIFECYCLE_FIELDS_ARE_TRIGGER_CONTROLLED'
            USING ERRCODE = '23514', CONSTRAINT = 'listings_lifecycle_fields_protected';
    END IF;
    IF actor = 'owner' AND OLD.owner_id IS DISTINCT FROM user_id THEN
        RAISE EXCEPTION 'LISTING_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;

    IF NEW.status IS DISTINCT FROM OLD.status THEN
        IF NEW.archived_from_status IS DISTINCT FROM OLD.archived_from_status
           OR NEW.archived_at IS DISTINCT FROM OLD.archived_at THEN
            RAISE EXCEPTION 'LISTING_ARCHIVE_FIELDS_ARE_TRIGGER_CONTROLLED'
                USING ERRCODE = '23514', CONSTRAINT = 'listings_archive_fields_protected';
        END IF;
        IF actor = 'owner' THEN
            IF OLD.suspended_at IS NOT NULL THEN
                RAISE EXCEPTION 'LISTING_SUSPENDED' USING ERRCODE = '23514', CONSTRAINT = 'listings_suspended_owner_lock';
            END IF;
            IF NEW.status = 'archived' AND OLD.status IN ('draft', 'active', 'rented', 'sold_out', 'unavailable') THEN
                NEW.archived_from_status := OLD.status; NEW.archived_at := now();
            ELSIF OLD.status = 'archived' AND OLD.archived_from_status IS NOT NULL AND NEW.status = OLD.archived_from_status THEN
                IF OLD.archived_at IS NULL OR OLD.archived_at < now() - interval '30 days' THEN
                    RAISE EXCEPTION 'LISTING_RESTORE_WINDOW_EXPIRED'
                        USING ERRCODE = '23514', CONSTRAINT = 'listings_restore_before_purge';
                END IF;
                NEW.archived_from_status := NULL; NEW.archived_at := NULL;
            ELSIF OLD.status = 'draft' AND NEW.status = 'active' THEN
                NULL;
            ELSIF OLD.status = 'active' AND NEW.status IN ('rented', 'sold_out', 'unavailable') THEN
                NULL;
            ELSIF OLD.status IN ('rented', 'sold_out', 'unavailable') AND NEW.status = 'active' THEN
                NULL;
            ELSE
                RAISE EXCEPTION 'LISTING_INVALID_TRANSITION'
                    USING ERRCODE = '23514', CONSTRAINT = 'listings_allowed_transition';
            END IF;
        ELSIF actor = 'system' THEN
            IF OLD.suspended_at IS NOT NULL THEN
                RAISE EXCEPTION 'LISTING_SUSPENDED' USING ERRCODE = '23514', CONSTRAINT = 'listings_suspended_system_lock';
            END IF;
            IF NEW.status <> 'archived' OR OLD.status NOT IN ('rented', 'sold_out', 'unavailable')
               OR OLD.status_changed_at >= now() - interval '30 days' THEN
                RAISE EXCEPTION 'LISTING_SYSTEM_ARCHIVE_NOT_DUE'
                    USING ERRCODE = '23514', CONSTRAINT = 'listings_system_archive_due';
            END IF;
            NEW.archived_from_status := OLD.status; NEW.archived_at := now();
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
REVOKE DELETE ON app.listings FROM rentra_api;

CREATE FUNCTION app._queue_and_delete_account_listings(p_user_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
BEGIN
    PERFORM set_config('app.user_id', p_user_id::text, true);
    PERFORM set_config('app.actor', 'account_deletion', true);
    INSERT INTO app.storage_deletions (bucket, path)
    SELECT 'listing-photos', paths.path
    FROM app.listings listing
    JOIN app.listing_photos photo ON photo.listing_id = listing.id
    CROSS JOIN LATERAL (VALUES (photo.storage_path), (photo.thumb_path)) paths(path)
    WHERE listing.owner_id = p_user_id AND paths.path IS NOT NULL;
    DELETE FROM app.listings WHERE owner_id = p_user_id;
    PERFORM set_config('app.actor', '', true);
    PERFORM set_config('app.user_id', '', true);
END;
$$;

CREATE FUNCTION app.request_account_deletion()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE user_id uuid;
BEGIN
    BEGIN
        user_id := nullif(current_setting('app.user_id', true), '')::uuid;
    EXCEPTION WHEN invalid_text_representation THEN user_id := NULL;
    END;
    IF user_id IS NULL THEN RAISE EXCEPTION 'ACCOUNT_DELETION_USER_REQUIRED' USING ERRCODE = '28000'; END IF;
    UPDATE app.profiles SET deletion_requested_at = COALESCE(deletion_requested_at, now()) WHERE id = user_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'ACCOUNT_DELETION_PROFILE_NOT_FOUND' USING ERRCODE = 'P0002'; END IF;
    PERFORM app._queue_and_delete_account_listings(user_id);
END;
$$;

CREATE FUNCTION app.list_stuck_account_deletions(p_limit integer)
RETURNS TABLE(user_id uuid)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE profile_row record;
BEGIN
    FOR profile_row IN
        SELECT profile.id
        FROM app.profiles profile
        WHERE profile.deletion_requested_at < now() - interval '5 minutes'
        ORDER BY profile.deletion_requested_at, profile.id
        LIMIT least(greatest(p_limit, 1), 100)
        FOR UPDATE OF profile SKIP LOCKED
    LOOP
        PERFORM app._queue_and_delete_account_listings(profile_row.id);
        user_id := profile_row.id;
        RETURN NEXT;
    END LOOP;
END;
$$;

REVOKE ALL ON FUNCTION app._queue_and_delete_account_listings(uuid) FROM PUBLIC, anon, authenticated, rentra_api;
REVOKE ALL ON FUNCTION app.request_account_deletion() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.list_stuck_account_deletions(integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.request_account_deletion() TO rentra_api;
GRANT EXECUTE ON FUNCTION app.list_stuck_account_deletions(integer) TO rentra_api;
