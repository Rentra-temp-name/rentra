CREATE OR REPLACE FUNCTION app.set_listing_status(p_listing_id uuid, p_new_status text)
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
    IF p_new_status = 'active' AND NOT EXISTS (
        SELECT 1 FROM app.profiles AS profile
        WHERE profile.id = user_id
          AND profile.whatsapp IS NOT NULL
          AND btrim(profile.whatsapp) <> ''
    ) THEN
        RAISE EXCEPTION 'WHATSAPP_REQUIRED' USING ERRCODE = 'P0001';
    END IF;
    UPDATE app.listings SET status = p_new_status
    WHERE id = listing.id AND owner_id = user_id
    RETURNING * INTO listing;
    PERFORM set_config('app.actor', '', true);
    RETURN listing;
END;
$$;

CREATE OR REPLACE FUNCTION app.restore_listing(p_listing_id uuid)
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
    IF listing.archived_from_status = 'active' AND NOT EXISTS (
        SELECT 1 FROM app.profiles AS profile
        WHERE profile.id = user_id
          AND profile.whatsapp IS NOT NULL
          AND btrim(profile.whatsapp) <> ''
    ) THEN
        RAISE EXCEPTION 'WHATSAPP_REQUIRED' USING ERRCODE = 'P0001';
    END IF;
    UPDATE app.listings SET status = listing.archived_from_status
    WHERE id = listing.id AND owner_id = user_id
    RETURNING * INTO listing;
    PERFORM set_config('app.actor', '', true);
    RETURN listing;
END;
$$;

CREATE FUNCTION app.guard_profile_whatsapp_clear()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
BEGIN
    IF NEW.whatsapp IS DISTINCT FROM OLD.whatsapp
       AND (NEW.whatsapp IS NULL OR btrim(NEW.whatsapp) = '')
       AND EXISTS (
           SELECT 1 FROM app.listings AS listing
           WHERE listing.owner_id = NEW.id AND listing.status = 'active'
       ) THEN
        RAISE EXCEPTION 'WHATSAPP_REQUIRED_FOR_ACTIVE_LISTING' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION app.guard_profile_whatsapp_clear() FROM PUBLIC, anon, authenticated, rentra_api;

CREATE TRIGGER profiles_whatsapp_required_for_active_listing
BEFORE UPDATE OF whatsapp ON app.profiles
FOR EACH ROW EXECUTE FUNCTION app.guard_profile_whatsapp_clear();

CREATE FUNCTION app.clear_my_whatsapp(p_confirm boolean)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    user_id uuid;
    active_count integer;
    archived_count integer;
BEGIN
    BEGIN
        user_id := nullif(current_setting('app.user_id', true), '')::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
        user_id := NULL;
    END;
    IF user_id IS NULL THEN
        RAISE EXCEPTION 'PROFILE_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;

    PERFORM 1
    FROM app.profiles AS profile
    WHERE profile.id = user_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'PROFILE_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;

    PERFORM set_config('app.actor', 'owner', true);
    SELECT count(*) INTO active_count
    FROM app.listings AS listing
    WHERE listing.owner_id = user_id
      AND listing.status = 'active'
      AND listing.suspended_at IS NULL;

    IF p_confirm IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'WHATSAPP_CLEAR_ARCHIVES_LISTINGS'
            USING ERRCODE = 'P0001', DETAIL = active_count::text;
    END IF;

    UPDATE app.listings
    SET status = 'archived'
    WHERE owner_id = user_id
      AND status = 'active'
      AND suspended_at IS NULL;
    GET DIAGNOSTICS archived_count = ROW_COUNT;

    UPDATE app.profiles
    SET whatsapp = NULL
    WHERE id = user_id;

    PERFORM set_config('app.actor', '', true);
    RETURN archived_count;
END;
$$;

REVOKE ALL ON FUNCTION app.clear_my_whatsapp(boolean) FROM PUBLIC, anon, authenticated, rentra_api;
GRANT EXECUTE ON FUNCTION app.clear_my_whatsapp(boolean) TO rentra_api;
