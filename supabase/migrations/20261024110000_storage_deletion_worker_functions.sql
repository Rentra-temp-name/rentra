CREATE FUNCTION app.claim_storage_deletions(p_limit integer)
RETURNS TABLE(id bigint, bucket text, path text)
LANGUAGE sql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
    UPDATE app.storage_deletions AS deletion
    SET attempts = deletion.attempts + 1,
        next_attempt_at = now() + interval '5 minutes'
    WHERE deletion.id IN (
        SELECT candidate.id
        FROM app.storage_deletions AS candidate
        WHERE candidate.done_at IS NULL AND candidate.next_attempt_at <= now()
        ORDER BY candidate.next_attempt_at, candidate.id
        LIMIT least(greatest(p_limit, 1), 100)
        FOR UPDATE SKIP LOCKED
    )
    RETURNING deletion.id, deletion.bucket, deletion.path;
$$;

CREATE FUNCTION app.complete_storage_deletion(p_id bigint)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
    UPDATE app.storage_deletions
    SET done_at = now(), last_error = NULL
    WHERE id = p_id AND done_at IS NULL;
$$;

CREATE FUNCTION app.fail_storage_deletion(p_id bigint, p_error text)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
    UPDATE app.storage_deletions
    SET last_error = left(p_error, 200),
        next_attempt_at = now() + least(power(2, attempts), 360) * interval '1 minute'
    WHERE id = p_id AND done_at IS NULL;
$$;

REVOKE ALL ON FUNCTION app.claim_storage_deletions(integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.complete_storage_deletion(bigint) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.fail_storage_deletion(bigint, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.claim_storage_deletions(integer) TO rentra_api;
GRANT EXECUTE ON FUNCTION app.complete_storage_deletion(bigint) TO rentra_api;
GRANT EXECUTE ON FUNCTION app.fail_storage_deletion(bigint, text) TO rentra_api;
