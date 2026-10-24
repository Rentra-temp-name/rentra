CREATE FUNCTION app.connect_listing_counted(p_listing_id uuid)
RETURNS TABLE (wa_link text, inserted boolean)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
    v_user_id uuid;
    v_exists boolean;
    v_link text;
BEGIN
    v_user_id := nullif(current_setting('app.user_id', true), '')::uuid;
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'PROFILE_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtext(v_user_id::text || ':' || p_listing_id::text));
    SELECT EXISTS (
        SELECT 1 FROM app.connections
        WHERE user_id = v_user_id AND listing_id = p_listing_id
    ) INTO v_exists;
    SELECT app.connect_listing(p_listing_id) INTO v_link;
    RETURN QUERY SELECT v_link, NOT v_exists;
END;
$$;

REVOKE ALL ON FUNCTION app.connect_listing_counted(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.connect_listing_counted(uuid) TO rentra_api;

CREATE FUNCTION app.get_ops_metrics()
RETURNS TABLE (kind text, job text, value double precision)
LANGUAGE sql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
    SELECT 'job_last_success_timestamp'::text, runs.job,
           extract(epoch FROM max(runs.finished_at))::double precision
    FROM app.job_runs AS runs
    WHERE runs.error IS NULL
    GROUP BY runs.job
    UNION ALL
    SELECT 'storage_deletions_backlog', NULL::text,
           count(*)::double precision
    FROM app.storage_deletions
    WHERE done_at IS NULL
    UNION ALL
    SELECT 'storage_deletions_oldest_pending_seconds', NULL::text,
           coalesce(extract(epoch FROM now() - min(created_at)), 0)::double precision
    FROM app.storage_deletions
    WHERE done_at IS NULL;
$$;

REVOKE ALL ON FUNCTION app.get_ops_metrics() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.get_ops_metrics() TO rentra_api;
