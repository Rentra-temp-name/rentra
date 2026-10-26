CREATE TABLE app.listings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL REFERENCES app.profiles(id) ON DELETE CASCADE,
    title text NOT NULL,
    rent_amount numeric(12, 2) NOT NULL,
    size_unit text,
    point extensions.geography(Point, 4326) NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    archived_from_status text,
    archived_at timestamptz,
    status_changed_at timestamptz NOT NULL DEFAULT now(),
    suspended_at timestamptz,
    suspended_by uuid,
    suspended_reason text,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT listings_rent_amount_positive_check
        CHECK (rent_amount > 0 AND rent_amount <> 'NaN'::numeric),
    CONSTRAINT listings_size_unit_check
        CHECK (size_unit IS NULL OR size_unit IN ('aana', 'ropani', 'sq_ft')),
    CONSTRAINT listings_status_check
        CHECK (status IN ('draft', 'active', 'rented', 'sold_out', 'unavailable', 'archived')),
    CONSTRAINT listings_archived_from_status_check
        CHECK (archived_from_status IS NULL OR archived_from_status IN
            ('draft', 'active', 'rented', 'sold_out', 'unavailable')),
    CONSTRAINT listings_version_positive_check CHECK (version > 0),
    CONSTRAINT listings_point_nepal_bounds_check CHECK (
        extensions.st_x(point::extensions.geometry) <> 'NaN'::float8
        AND extensions.st_y(point::extensions.geometry) <> 'NaN'::float8
        AND extensions.st_x(point::extensions.geometry) BETWEEN 80.0 AND 88.3
        AND extensions.st_y(point::extensions.geometry) BETWEEN 26.3 AND 30.5
    )
);

CREATE INDEX listings_owner_status_idx ON app.listings (owner_id, status);
CREATE INDEX listings_status_changed_at_idx ON app.listings (status, status_changed_at);
CREATE INDEX listings_archived_at_idx ON app.listings (archived_at) WHERE status = 'archived';
CREATE INDEX listings_public_point_gist_idx
    ON app.listings USING gist (point)
    WHERE status = 'active' AND suspended_at IS NULL;

ALTER TABLE app.listings ENABLE ROW LEVEL SECURITY;

CREATE POLICY listings_select_public_or_owner ON app.listings
    FOR SELECT TO rentra_api
    USING (
        owner_id = nullif(current_setting('app.user_id', true), '')::uuid
        OR (status = 'active' AND suspended_at IS NULL)
    );

CREATE POLICY listings_insert_owner ON app.listings
    FOR INSERT TO rentra_api
    WITH CHECK (owner_id = nullif(current_setting('app.user_id', true), '')::uuid);

CREATE POLICY listings_update_owner ON app.listings
    FOR UPDATE TO rentra_api
    USING (owner_id = nullif(current_setting('app.user_id', true), '')::uuid)
    WITH CHECK (owner_id = nullif(current_setting('app.user_id', true), '')::uuid);

CREATE POLICY listings_delete_owner ON app.listings
    FOR DELETE TO rentra_api
    USING (owner_id = nullif(current_setting('app.user_id', true), '')::uuid);

REVOKE ALL ON app.listings FROM PUBLIC, anon, authenticated, rentra_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON app.listings TO rentra_api;
