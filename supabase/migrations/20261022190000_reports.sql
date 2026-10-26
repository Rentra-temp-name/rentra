CREATE TABLE app.reports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    reporter_id uuid REFERENCES app.profiles(id) ON DELETE SET NULL,
    listing_id uuid REFERENCES app.listings(id) ON DELETE SET NULL,
    snapshot_title text NOT NULL,
    snapshot_whatsapp text,
    reason text NOT NULL,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    resolved_by uuid REFERENCES app.profiles(id) ON DELETE SET NULL,
    resolved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT reports_reason_length_check CHECK (char_length(btrim(reason)) BETWEEN 1 AND 1000),
    CONSTRAINT reports_reporter_listing_key UNIQUE (reporter_id, listing_id)
);

CREATE INDEX reports_reporter_id_idx ON app.reports (reporter_id);
CREATE INDEX reports_listing_id_idx ON app.reports (listing_id);
CREATE INDEX reports_resolved_by_idx ON app.reports (resolved_by);
CREATE INDEX reports_open_created_at_idx
    ON app.reports (created_at DESC, id DESC)
    WHERE status = 'open';

ALTER TABLE app.reports ENABLE ROW LEVEL SECURITY;
CREATE POLICY reports_select_own ON app.reports
    FOR SELECT TO rentra_api
    USING (reporter_id = nullif(current_setting('app.user_id', true), '')::uuid);

REVOKE ALL ON app.reports FROM PUBLIC, anon, authenticated, rentra_api;
GRANT SELECT ON app.reports TO rentra_api;
