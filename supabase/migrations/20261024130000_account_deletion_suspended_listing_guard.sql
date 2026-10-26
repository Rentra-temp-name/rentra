CREATE FUNCTION app.guard_account_deletion_listing_suspension()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE user_id uuid;
BEGIN
    IF current_setting('app.actor', true) = 'account_deletion' THEN
        BEGIN
            user_id := nullif(current_setting('app.user_id', true), '')::uuid;
        EXCEPTION WHEN invalid_text_representation THEN
            user_id := NULL;
        END;
        IF user_id IS NULL OR OLD.owner_id IS DISTINCT FROM user_id THEN
            RAISE EXCEPTION 'LISTING_NOT_FOUND' USING ERRCODE = 'P0002';
        END IF;
        IF OLD.suspended_at IS NOT NULL THEN
            RAISE EXCEPTION 'LISTING_SUSPENDED'
                USING ERRCODE = '23514', CONSTRAINT = 'listings_suspended_account_deletion_lock';
        END IF;
    END IF;
    RETURN OLD;
END;
$$;

REVOKE ALL ON FUNCTION app.guard_account_deletion_listing_suspension() FROM PUBLIC, anon, authenticated, rentra_api;
CREATE TRIGGER listings_account_deletion_suspension_guard
BEFORE DELETE ON app.listings
FOR EACH ROW EXECUTE FUNCTION app.guard_account_deletion_listing_suspension();

CREATE OR REPLACE FUNCTION app.request_account_deletion()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    v_user_id uuid;
    v_locked_user_id uuid;
BEGIN
    BEGIN
        v_user_id := nullif(current_setting('app.user_id', true), '')::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
        v_user_id := NULL;
    END;
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'ACCOUNT_DELETION_USER_REQUIRED' USING ERRCODE = '28000';
    END IF;

    SELECT profile.id INTO v_locked_user_id
    FROM app.profiles AS profile
    WHERE profile.id = v_user_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ACCOUNT_DELETION_PROFILE_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;
    IF EXISTS (
        SELECT 1 FROM app.listings AS listing
        WHERE listing.owner_id = v_user_id AND listing.suspended_at IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'ACCOUNT_HAS_SUSPENDED_LISTING' USING ERRCODE = '23514';
    END IF;

    UPDATE app.profiles
    SET deletion_requested_at = COALESCE(deletion_requested_at, now())
    WHERE id = v_user_id;
    PERFORM app._queue_and_delete_account_listings(v_user_id);
END;
$$;

CREATE OR REPLACE FUNCTION app.list_stuck_account_deletions(p_limit integer)
RETURNS TABLE(user_id uuid)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE profile_row record;
BEGIN
    FOR profile_row IN
        SELECT profile.id
        FROM app.profiles AS profile
        WHERE profile.deletion_requested_at < now() - interval '5 minutes'
          AND NOT EXISTS (
              SELECT 1 FROM app.listings AS listing
              WHERE listing.owner_id = profile.id AND listing.suspended_at IS NOT NULL
          )
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

REVOKE ALL ON FUNCTION app.request_account_deletion() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.list_stuck_account_deletions(integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.request_account_deletion() TO rentra_api;
GRANT EXECUTE ON FUNCTION app.list_stuck_account_deletions(integer) TO rentra_api;
