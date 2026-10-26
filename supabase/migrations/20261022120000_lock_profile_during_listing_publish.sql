-- Serialize listing activation checks with profile WhatsApp clears.

CREATE OR REPLACE FUNCTION app.publish_listing(p_listing_id uuid)
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
    PERFORM 1 FROM app.profiles AS profile WHERE profile.id = user_id FOR SHARE;


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
    PERFORM 1 FROM app.profiles AS profile WHERE profile.id = user_id FOR SHARE;

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
    PERFORM 1 FROM app.profiles AS profile WHERE profile.id = user_id FOR SHARE;

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
