CREATE FUNCTION app.save_listing(p_listing_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    v_user_id uuid;
    v_owner_id uuid;
    v_status text;
    v_suspended_at timestamptz;
BEGIN
    v_user_id := nullif(current_setting('app.user_id', true), '')::uuid;
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'PROFILE_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;

    SELECT listing.owner_id, listing.status, listing.suspended_at
    INTO v_owner_id, v_status, v_suspended_at
    FROM app.listings AS listing
    WHERE listing.id = p_listing_id;
    IF NOT FOUND OR v_status <> 'active' OR v_suspended_at IS NOT NULL THEN
        RAISE EXCEPTION 'LISTING_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;
    IF v_owner_id = v_user_id THEN
        RAISE EXCEPTION 'SAVE_OWN_LISTING' USING ERRCODE = 'P0001';
    END IF;

    INSERT INTO app.saved_listings (user_id, listing_id)
    VALUES (v_user_id, p_listing_id)
    ON CONFLICT (user_id, listing_id) DO NOTHING;
    RETURN true;
END;
$$;

CREATE FUNCTION app.unsave_listing(p_listing_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    v_user_id uuid;
    v_listing_id uuid;
BEGIN
    v_user_id := nullif(current_setting('app.user_id', true), '')::uuid;
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'PROFILE_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;

    SELECT listing.id INTO v_listing_id
    FROM app.listings AS listing
    WHERE listing.id = p_listing_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'LISTING_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;

    DELETE FROM app.saved_listings AS saved
    WHERE saved.user_id = v_user_id AND saved.listing_id = p_listing_id;
    RETURN true;
END;
$$;

CREATE FUNCTION app.get_my_saved(
    p_before_created_at timestamptz,
    p_before_id uuid,
    p_limit integer
)
RETURNS TABLE (
    listing_id uuid,
    listing_title text,
    rent numeric,
    visible boolean,
    wa_link text,
    saved_at timestamptz
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
    SELECT listing.id,
           listing.title,
           listing.rent_amount,
           listing.status = 'active' AND listing.suspended_at IS NULL,
           CASE WHEN listing.status = 'active' AND listing.suspended_at IS NULL
                     AND profile.whatsapp IS NOT NULL AND btrim(profile.whatsapp) <> ''
                THEN 'https://wa.me/' || regexp_replace(profile.whatsapp, '[^0-9]', '', 'g')
                ELSE NULL
           END,
           saved.created_at
    FROM app.saved_listings AS saved
    JOIN app.listings AS listing ON listing.id = saved.listing_id
    JOIN app.profiles AS profile ON profile.id = listing.owner_id
    WHERE saved.user_id = nullif(current_setting('app.user_id', true), '')::uuid
      AND (p_before_created_at IS NULL OR
           (saved.created_at, saved.listing_id) < (p_before_created_at, p_before_id))
    ORDER BY saved.created_at DESC, saved.listing_id DESC
    LIMIT least(greatest(p_limit, 1), 51);
$$;

CREATE FUNCTION app.report_listing(p_listing_id uuid, p_reason text)
RETURNS app.reports
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    v_user_id uuid;
    v_owner_id uuid;
    v_listing_title text;
    v_owner_whatsapp text;
    v_report app.reports%ROWTYPE;
    v_recent_count integer;
    v_oldest_recent timestamptz;
    v_retry_after integer;
BEGIN
    SELECT profile.id INTO v_user_id
    FROM app.profiles AS profile
    WHERE profile.id = nullif(current_setting('app.user_id', true), '')::uuid
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'PROFILE_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;

    SELECT report.* INTO v_report
    FROM app.reports AS report
    WHERE report.reporter_id = v_user_id AND report.listing_id = p_listing_id;
    IF FOUND THEN
        RETURN v_report;
    END IF;

    SELECT listing.owner_id, listing.title, profile.whatsapp
    INTO v_owner_id, v_listing_title, v_owner_whatsapp
    FROM app.listings AS listing
    JOIN app.profiles AS profile ON profile.id = listing.owner_id
    WHERE listing.id = p_listing_id
      AND listing.status = 'active'
      AND listing.suspended_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'LISTING_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;
    IF v_owner_id = v_user_id THEN
        RAISE EXCEPTION 'REPORT_OWN_LISTING' USING ERRCODE = 'P0001';
    END IF;
    IF p_reason IS NULL OR char_length(btrim(p_reason)) NOT BETWEEN 1 AND 1000 THEN
        RAISE EXCEPTION 'INVALID_REPORT_REASON' USING ERRCODE = 'P0001';
    END IF;

    SELECT count(*)::integer, min(report.created_at)
    INTO v_recent_count, v_oldest_recent
    FROM app.reports AS report
    WHERE report.reporter_id = v_user_id
      AND report.created_at >= now() - interval '24 hours';
    IF v_recent_count >= 10 THEN
        v_retry_after := greatest(
            1,
            ceil(extract(epoch FROM (v_oldest_recent + interval '24 hours' - now())))::integer
        );
        RAISE EXCEPTION 'REPORT_LIMIT'
            USING ERRCODE = 'P0001', DETAIL = v_retry_after::text;
    END IF;

    INSERT INTO app.reports (
        reporter_id, listing_id, snapshot_title, snapshot_whatsapp, reason
    ) VALUES (
        v_user_id, p_listing_id, v_listing_title, v_owner_whatsapp, btrim(p_reason)
    )
    RETURNING * INTO v_report;
    RETURN v_report;
END;
$$;

CREATE FUNCTION app.admin_list_reports(
    p_status text,
    p_before_created_at timestamptz,
    p_before_id uuid,
    p_limit integer
)
RETURNS SETOF app.reports
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    v_admin_id uuid;
BEGIN
    v_admin_id := nullif(current_setting('app.user_id', true), '')::uuid;
    IF v_admin_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM app.admins AS admin WHERE admin.user_id = v_admin_id
    ) THEN
        RAISE EXCEPTION 'ADMIN_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;
    IF p_status IS NULL OR p_status NOT IN ('open', 'resolved') THEN
        RAISE EXCEPTION 'INVALID_REPORT_STATUS' USING ERRCODE = 'P0001';
    END IF;

    RETURN QUERY
    SELECT report.*
    FROM app.reports AS report
    WHERE report.status = p_status
      AND (p_before_created_at IS NULL OR
           (report.created_at, report.id) < (p_before_created_at, p_before_id))
    ORDER BY report.created_at DESC, report.id DESC
    LIMIT least(greatest(p_limit, 1), 51);
END;
$$;

CREATE OR REPLACE FUNCTION app.admin_resolve_report(p_report_id uuid, p_note text DEFAULT NULL)
RETURNS app.reports
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    v_admin_id uuid;
    v_report app.reports%ROWTYPE;
    v_note text;
BEGIN
    v_admin_id := nullif(current_setting('app.user_id', true), '')::uuid;
    IF v_admin_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM app.admins AS admin WHERE admin.user_id = v_admin_id
    ) THEN
        RAISE EXCEPTION 'ADMIN_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;

    v_note := nullif(btrim(p_note), '');
    IF v_note IS NOT NULL AND char_length(v_note) > 500 THEN
        RAISE EXCEPTION 'INVALID_ADMIN_NOTE' USING ERRCODE = 'P0001';
    END IF;

    SELECT report.* INTO v_report
    FROM app.reports AS report
    WHERE report.id = p_report_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'REPORT_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;
    IF v_report.status = 'resolved' THEN
        RETURN v_report;
    END IF;

    UPDATE app.reports AS report
    SET status = 'resolved', resolved_by = v_admin_id, resolved_at = now()
    WHERE report.id = p_report_id
    RETURNING report.* INTO v_report;
    INSERT INTO app.admin_actions (admin_id, action, listing_id, reason)
    VALUES (v_admin_id, 'resolve_report', v_report.listing_id, v_note);
    RETURN v_report;
END;
$$;

CREATE FUNCTION app.admin_suspend_listing(p_listing_id uuid, p_reason text)
RETURNS app.listings
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    v_admin_id uuid;
    v_listing app.listings%ROWTYPE;
BEGIN
    v_admin_id := nullif(current_setting('app.user_id', true), '')::uuid;
    IF v_admin_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM app.admins AS admin WHERE admin.user_id = v_admin_id
    ) THEN
        RAISE EXCEPTION 'ADMIN_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;
    IF p_reason IS NULL OR char_length(btrim(p_reason)) NOT BETWEEN 1 AND 500 THEN
        RAISE EXCEPTION 'ADMIN_REASON_REQUIRED' USING ERRCODE = 'P0001';
    END IF;

    SELECT listing.* INTO v_listing
    FROM app.listings AS listing
    WHERE listing.id = p_listing_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'LISTING_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;
    IF v_listing.suspended_at IS NOT NULL THEN
        RAISE EXCEPTION 'LISTING_ALREADY_SUSPENDED' USING ERRCODE = 'P0001';
    END IF;

    PERFORM set_config('app.actor', 'admin', true);
    UPDATE app.listings AS listing
    SET suspended_at = now(), suspended_by = v_admin_id, suspended_reason = btrim(p_reason)
    WHERE listing.id = p_listing_id
    RETURNING listing.* INTO v_listing;
    INSERT INTO app.admin_actions (admin_id, action, listing_id, reason)
    VALUES (v_admin_id, 'suspend', p_listing_id, btrim(p_reason));
    PERFORM set_config('app.actor', '', true);
    RETURN v_listing;
END;
$$;

CREATE FUNCTION app.admin_unsuspend_listing(p_listing_id uuid)
RETURNS app.listings
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    v_admin_id uuid;
    v_listing app.listings%ROWTYPE;
BEGIN
    v_admin_id := nullif(current_setting('app.user_id', true), '')::uuid;
    IF v_admin_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM app.admins AS admin WHERE admin.user_id = v_admin_id
    ) THEN
        RAISE EXCEPTION 'ADMIN_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;

    SELECT listing.* INTO v_listing
    FROM app.listings AS listing
    WHERE listing.id = p_listing_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'LISTING_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;
    IF v_listing.suspended_at IS NULL THEN
        RAISE EXCEPTION 'LISTING_NOT_SUSPENDED' USING ERRCODE = 'P0001';
    END IF;

    PERFORM set_config('app.actor', 'admin', true);
    UPDATE app.listings AS listing
    SET suspended_at = NULL, suspended_by = NULL, suspended_reason = NULL
    WHERE listing.id = p_listing_id
    RETURNING listing.* INTO v_listing;
    INSERT INTO app.admin_actions (admin_id, action, listing_id, reason)
    VALUES (v_admin_id, 'unsuspend', p_listing_id, NULL);
    PERFORM set_config('app.actor', '', true);
    RETURN v_listing;
END;
$$;

CREATE FUNCTION app.notify_saved_listing_changes()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
BEGIN
    INSERT INTO app.notifications (user_id, kind, listing_id, other_user_id)
    SELECT saved.user_id, 'saved_listing_changed', NEW.id, NULL
    FROM app.saved_listings AS saved
    WHERE saved.listing_id = NEW.id
      AND saved.user_id <> NEW.owner_id;
    RETURN NEW;
END;
$$;

CREATE TRIGGER listings_notify_saved_listing_changes
AFTER UPDATE ON app.listings
FOR EACH ROW
WHEN (
    OLD.rent_amount IS DISTINCT FROM NEW.rent_amount
    OR ((OLD.status = 'active' AND OLD.suspended_at IS NULL)
        IS DISTINCT FROM (NEW.status = 'active' AND NEW.suspended_at IS NULL))
)
EXECUTE FUNCTION app.notify_saved_listing_changes();

REVOKE ALL ON FUNCTION app.save_listing(uuid) FROM PUBLIC, anon, authenticated, rentra_api;
REVOKE ALL ON FUNCTION app.unsave_listing(uuid) FROM PUBLIC, anon, authenticated, rentra_api;
REVOKE ALL ON FUNCTION app.get_my_saved(timestamptz, uuid, integer) FROM PUBLIC, anon, authenticated, rentra_api;
REVOKE ALL ON FUNCTION app.report_listing(uuid, text) FROM PUBLIC, anon, authenticated, rentra_api;
REVOKE ALL ON FUNCTION app.admin_list_reports(text, timestamptz, uuid, integer) FROM PUBLIC, anon, authenticated, rentra_api;
REVOKE ALL ON FUNCTION app.admin_resolve_report(uuid, text) FROM PUBLIC, anon, authenticated, rentra_api;
REVOKE ALL ON FUNCTION app.admin_suspend_listing(uuid, text) FROM PUBLIC, anon, authenticated, rentra_api;
REVOKE ALL ON FUNCTION app.admin_unsuspend_listing(uuid) FROM PUBLIC, anon, authenticated, rentra_api;
REVOKE ALL ON FUNCTION app.notify_saved_listing_changes() FROM PUBLIC, anon, authenticated, rentra_api;

GRANT EXECUTE ON FUNCTION app.save_listing(uuid) TO rentra_api;
GRANT EXECUTE ON FUNCTION app.unsave_listing(uuid) TO rentra_api;
GRANT EXECUTE ON FUNCTION app.get_my_saved(timestamptz, uuid, integer) TO rentra_api;
GRANT EXECUTE ON FUNCTION app.report_listing(uuid, text) TO rentra_api;
GRANT EXECUTE ON FUNCTION app.admin_list_reports(text, timestamptz, uuid, integer) TO rentra_api;
GRANT EXECUTE ON FUNCTION app.admin_resolve_report(uuid, text) TO rentra_api;
GRANT EXECUTE ON FUNCTION app.admin_suspend_listing(uuid, text) TO rentra_api;
GRANT EXECUTE ON FUNCTION app.admin_unsuspend_listing(uuid) TO rentra_api;
GRANT EXECUTE ON FUNCTION app.notify_saved_listing_changes() TO rentra_api;
