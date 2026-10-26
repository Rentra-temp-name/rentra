CREATE OR REPLACE FUNCTION app.job_purge_archived_listings()
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS $$
DECLARE run_id bigint; changed integer;
BEGIN
    IF NOT pg_try_advisory_xact_lock(hashtext('rentra_job_purge_archived_listings')) THEN RETURN NULL; END IF;
    INSERT INTO app.job_runs (job, started_at) VALUES ('purge_archived_listings', clock_timestamp()) RETURNING id INTO run_id;
    PERFORM set_config('app.actor', 'system', true);
    BEGIN
        WITH deleted AS (
            DELETE FROM app.listings
            WHERE status = 'archived' AND archived_at < now() - interval '30 days' AND suspended_at IS NULL
            RETURNING id
        ), queued AS (
            INSERT INTO app.storage_deletions (bucket, path)
            SELECT 'listing-photos', paths.path FROM app.listing_photos photo
            JOIN deleted ON deleted.id = photo.listing_id
            CROSS JOIN LATERAL (VALUES (photo.storage_path), (photo.thumb_path)) paths(path)
            WHERE paths.path IS NOT NULL
        )
        SELECT count(*) INTO changed FROM deleted;
        PERFORM set_config('app.actor', '', true);
    EXCEPTION WHEN OTHERS THEN
        PERFORM set_config('app.actor', '', true);
        UPDATE app.job_runs SET error = SQLERRM, finished_at = clock_timestamp() WHERE id = run_id;
        RETURN NULL;
    END;
    UPDATE app.job_runs SET rows = changed, finished_at = clock_timestamp() WHERE id = run_id;
    RETURN changed;
END; $$;

CREATE OR REPLACE FUNCTION app.job_purge_abandoned_drafts()
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS $$
DECLARE run_id bigint; changed integer;
BEGIN
    IF NOT pg_try_advisory_xact_lock(hashtext('rentra_job_purge_abandoned_drafts')) THEN RETURN NULL; END IF;
    INSERT INTO app.job_runs (job, started_at) VALUES ('purge_abandoned_drafts', clock_timestamp()) RETURNING id INTO run_id;
    PERFORM set_config('app.actor', 'system', true);
    BEGIN
        WITH deleted AS (
            DELETE FROM app.listings
            WHERE status = 'draft' AND updated_at < now() - interval '30 days' AND suspended_at IS NULL
            RETURNING id
        ), queued AS (
            INSERT INTO app.storage_deletions (bucket, path)
            SELECT 'listing-photos', paths.path FROM app.listing_photos photo
            JOIN deleted ON deleted.id = photo.listing_id
            CROSS JOIN LATERAL (VALUES (photo.storage_path), (photo.thumb_path)) paths(path)
            WHERE paths.path IS NOT NULL
        )
        SELECT count(*) INTO changed FROM deleted;
        PERFORM set_config('app.actor', '', true);
    EXCEPTION WHEN OTHERS THEN
        PERFORM set_config('app.actor', '', true);
        UPDATE app.job_runs SET error = SQLERRM, finished_at = clock_timestamp() WHERE id = run_id;
        RETURN NULL;
    END;
    UPDATE app.job_runs SET rows = changed, finished_at = clock_timestamp() WHERE id = run_id;
    RETURN changed;
END; $$;

REVOKE ALL ON FUNCTION app.job_purge_archived_listings() FROM PUBLIC, anon, authenticated, rentra_api;
REVOKE ALL ON FUNCTION app.job_purge_abandoned_drafts() FROM PUBLIC, anon, authenticated, rentra_api;
