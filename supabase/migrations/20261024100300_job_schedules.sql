DO $$
BEGIN
    IF to_regnamespace('cron') IS NOT NULL THEN
        PERFORM cron.schedule('rentra-archive-stale-listings', '0 3 * * *', 'SELECT app.job_archive_stale_listings()');
        PERFORM cron.schedule('rentra-purge-archived-listings', '10 3 * * *', 'SELECT app.job_purge_archived_listings()');
        PERFORM cron.schedule('rentra-purge-abandoned-drafts', '20 3 * * *', 'SELECT app.job_purge_abandoned_drafts()');
    END IF;
END;
$$;
