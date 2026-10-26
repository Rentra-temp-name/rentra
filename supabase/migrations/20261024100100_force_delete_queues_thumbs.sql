CREATE OR REPLACE FUNCTION app.force_delete_listing(p_listing_id uuid)
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
    IF NOT FOUND THEN RAISE EXCEPTION 'LISTING_NOT_FOUND' USING ERRCODE = 'P0002'; END IF;
    PERFORM set_config('app.actor', 'owner', true);
    IF listing.suspended_at IS NOT NULL THEN
        RAISE EXCEPTION 'LISTING_SUSPENDED' USING ERRCODE = '23514';
    END IF;
    IF listing.status <> 'archived' THEN
        RAISE EXCEPTION 'LISTING_DELETE_REQUIRES_ARCHIVED'
            USING ERRCODE = '23514', CONSTRAINT = 'listings_delete_archived_only';
    END IF;

    SELECT COALESCE(array_agg(photo.storage_path ORDER BY photo.position, photo.id), ARRAY[]::text[])
    INTO photo_paths FROM app.listing_photos AS photo WHERE photo.listing_id = listing.id;

    IF to_regclass('app.storage_deletions') IS NOT NULL THEN
        INSERT INTO app.storage_deletions (bucket, path)
        SELECT 'listing-photos', paths.path
        FROM app.listing_photos AS photo
        CROSS JOIN LATERAL (VALUES (photo.storage_path), (photo.thumb_path)) AS paths(path)
        WHERE photo.listing_id = listing.id AND paths.path IS NOT NULL;
    END IF;
    DELETE FROM app.listings WHERE id = listing.id AND owner_id = user_id;
    PERFORM set_config('app.actor', '', true);
    RETURN photo_paths;
END;
$$;

REVOKE ALL ON FUNCTION app.force_delete_listing(uuid) FROM PUBLIC, anon, authenticated, rentra_api;
GRANT EXECUTE ON FUNCTION app.force_delete_listing(uuid) TO rentra_api;
