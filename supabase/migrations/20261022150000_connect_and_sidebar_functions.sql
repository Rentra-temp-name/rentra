CREATE FUNCTION app.connect_listing(p_listing_id uuid)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    v_user_id uuid;
    v_owner_id uuid;
    v_owner_whatsapp text;
    v_connection_id uuid;
    v_recent_count integer;
    v_oldest_recent timestamptz;
    v_retry_after integer;
    v_wa_link text;
BEGIN
    BEGIN
        v_user_id := nullif(current_setting('app.user_id', true), '')::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
        v_user_id := NULL;
    END;
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'PROFILE_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;

    SELECT listing.owner_id, profile.whatsapp
    INTO v_owner_id, v_owner_whatsapp
    FROM app.listings AS listing
    JOIN app.profiles AS profile ON profile.id = listing.owner_id
    WHERE listing.id = p_listing_id
      AND listing.status = 'active'
      AND listing.suspended_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'LISTING_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;
    IF v_owner_id = v_user_id THEN
        RAISE EXCEPTION 'CONNECT_OWN_LISTING' USING ERRCODE = 'P0001';
    END IF;

    IF v_owner_whatsapp IS NOT NULL AND btrim(v_owner_whatsapp) <> '' THEN
        v_wa_link := 'https://wa.me/' || regexp_replace(v_owner_whatsapp, '[^0-9]', '', 'g');
    END IF;

    IF EXISTS (
        SELECT 1 FROM app.connections AS connection
        WHERE connection.user_id = v_user_id
          AND connection.listing_id = p_listing_id
    ) THEN
        RETURN v_wa_link;
    END IF;

    SELECT count(*)::integer, min(connection.created_at)
    INTO v_recent_count, v_oldest_recent
    FROM app.connections AS connection
    WHERE connection.user_id = v_user_id
      AND connection.created_at >= now() - interval '24 hours';
    IF v_recent_count >= 50 THEN
        v_retry_after := greatest(
            1,
            ceil(extract(epoch FROM (v_oldest_recent + interval '24 hours' - now())))::integer
        );
        RAISE EXCEPTION 'CONNECT_LIMIT'
            USING ERRCODE = 'P0001', DETAIL = v_retry_after::text;
    END IF;

    INSERT INTO app.connections (user_id, listing_id)
    VALUES (v_user_id, p_listing_id)
    ON CONFLICT (user_id, listing_id) DO NOTHING
    RETURNING id INTO v_connection_id;

    IF v_connection_id IS NOT NULL THEN
        INSERT INTO app.notifications (user_id, kind, listing_id, other_user_id)
        VALUES
            (v_user_id, 'property_connected', p_listing_id, v_owner_id),
            (v_owner_id, 'profile_connected', p_listing_id, v_user_id);
    END IF;
    RETURN v_wa_link;
END;
$$;

REVOKE ALL ON FUNCTION app.connect_listing(uuid) FROM PUBLIC, anon, authenticated, rentra_api;
GRANT EXECUTE ON FUNCTION app.connect_listing(uuid) TO rentra_api;

CREATE FUNCTION app.get_connected_profile(p_other_id uuid)
RETURNS TABLE (display_name text, whatsapp text, wa_link text)
LANGUAGE sql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
    SELECT profile.display_name,
           profile.whatsapp,
           CASE WHEN profile.whatsapp IS NULL OR btrim(profile.whatsapp) = '' THEN NULL
                ELSE 'https://wa.me/' || regexp_replace(profile.whatsapp, '[^0-9]', '', 'g')
           END
    FROM app.profiles AS profile
    WHERE profile.id = p_other_id
      AND profile.deletion_requested_at IS NULL
      AND (
          EXISTS (
              SELECT 1
              FROM app.connections AS connection
              JOIN app.listings AS listing ON listing.id = connection.listing_id
              WHERE connection.user_id = p_other_id
                AND listing.owner_id = nullif(current_setting('app.user_id', true), '')::uuid
          )
          OR EXISTS (
              SELECT 1
              FROM app.connections AS connection
              JOIN app.listings AS listing ON listing.id = connection.listing_id
              WHERE connection.user_id = nullif(current_setting('app.user_id', true), '')::uuid
                AND listing.owner_id = p_other_id
                AND listing.status = 'active'
                AND listing.suspended_at IS NULL
          )
      );
$$;

REVOKE ALL ON FUNCTION app.get_connected_profile(uuid) FROM PUBLIC, anon, authenticated, rentra_api;
GRANT EXECUTE ON FUNCTION app.get_connected_profile(uuid) TO rentra_api;

CREATE FUNCTION app.get_my_connections(
    p_before_created_at timestamptz,
    p_before_id uuid,
    p_limit integer
)
RETURNS TABLE (
    connection_id uuid,
    connection_created_at timestamptz,
    listing_id uuid,
    listing_title text,
    listing_public_visible boolean,
    wa_link text
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
    SELECT connection.id,
           connection.created_at,
           listing.id,
           listing.title,
           listing.status = 'active' AND listing.suspended_at IS NULL,
           CASE WHEN listing.status = 'active' AND listing.suspended_at IS NULL
                     AND profile.whatsapp IS NOT NULL AND btrim(profile.whatsapp) <> ''
                THEN 'https://wa.me/' || regexp_replace(profile.whatsapp, '[^0-9]', '', 'g')
                ELSE NULL
           END
    FROM app.connections AS connection
    JOIN app.listings AS listing ON listing.id = connection.listing_id
    JOIN app.profiles AS profile ON profile.id = listing.owner_id
    WHERE connection.user_id = nullif(current_setting('app.user_id', true), '')::uuid
      AND (p_before_created_at IS NULL OR
           (connection.created_at, connection.id) < (p_before_created_at, p_before_id))
    ORDER BY connection.created_at DESC, connection.id DESC
    LIMIT least(greatest(p_limit, 1), 51);
$$;

REVOKE ALL ON FUNCTION app.get_my_connections(timestamptz, uuid, integer)
    FROM PUBLIC, anon, authenticated, rentra_api;
GRANT EXECUTE ON FUNCTION app.get_my_connections(timestamptz, uuid, integer) TO rentra_api;

CREATE FUNCTION app.get_my_notifications(
    p_before_created_at timestamptz,
    p_before_id uuid,
    p_limit integer
)
RETURNS TABLE (
    notification_id uuid,
    notification_kind text,
    notification_created_at timestamptz,
    notification_read_at timestamptz,
    other_user_id uuid,
    other_user_display_name text,
    listing_id uuid,
    listing_title text
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
    SELECT notification.id,
           notification.kind,
           notification.created_at,
           notification.read_at,
           profile.id,
           profile.display_name,
           listing.id,
           listing.title
    FROM app.notifications AS notification
    LEFT JOIN app.profiles AS profile ON profile.id = notification.other_user_id
    LEFT JOIN app.listings AS listing ON listing.id = notification.listing_id
    WHERE notification.user_id = nullif(current_setting('app.user_id', true), '')::uuid
      AND (p_before_created_at IS NULL OR
           (notification.created_at, notification.id) < (p_before_created_at, p_before_id))
    ORDER BY notification.created_at DESC, notification.id DESC
    LIMIT least(greatest(p_limit, 1), 51);
$$;

REVOKE ALL ON FUNCTION app.get_my_notifications(timestamptz, uuid, integer)
    FROM PUBLIC, anon, authenticated, rentra_api;
GRANT EXECUTE ON FUNCTION app.get_my_notifications(timestamptz, uuid, integer) TO rentra_api;
