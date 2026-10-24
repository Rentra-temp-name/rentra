CREATE TABLE app.job_runs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job text NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    rows integer,
    error text
);
CREATE INDEX job_runs_job_started_at_idx ON app.job_runs (job, started_at DESC);
ALTER TABLE app.job_runs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON app.job_runs FROM PUBLIC, anon, authenticated, rentra_api;

CREATE TABLE app.storage_deletions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bucket text NOT NULL,
    path text NOT NULL,
    attempts integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    done_at timestamptz,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    last_error text
);
CREATE INDEX storage_deletions_due_idx ON app.storage_deletions (next_attempt_at)
    WHERE done_at IS NULL;
ALTER TABLE app.storage_deletions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON app.storage_deletions FROM PUBLIC, anon, authenticated, rentra_api;
