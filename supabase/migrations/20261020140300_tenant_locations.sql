CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions;

CREATE TABLE app.tenant_locations (
    user_id uuid PRIMARY KEY REFERENCES app.profiles(id) ON DELETE CASCADE,
    current_point extensions.geography(Point, 4326) NOT NULL,
    search_point extensions.geography(Point, 4326) NOT NULL,
    search_radius_km numeric(5, 2) NOT NULL DEFAULT 5
        CHECK (search_radius_km BETWEEN 1 AND 50),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT tenant_locations_current_point_nepal_grid_check CHECK (
        extensions.st_x(current_point::extensions.geometry) <> 'NaN'::float8
        AND extensions.st_y(current_point::extensions.geometry) <> 'NaN'::float8
        AND extensions.st_x(current_point::extensions.geometry) BETWEEN 80.0 AND 88.3
        AND extensions.st_y(current_point::extensions.geometry) BETWEEN 26.3 AND 30.5
        AND abs(
            extensions.st_x(current_point::extensions.geometry) * 100
            - round(extensions.st_x(current_point::extensions.geometry) * 100)
        ) < 0.000001
        AND abs(
            extensions.st_y(current_point::extensions.geometry) * 100
            - round(extensions.st_y(current_point::extensions.geometry) * 100)
        ) < 0.000001
    ),
    CONSTRAINT tenant_locations_search_point_nepal_grid_check CHECK (
        extensions.st_x(search_point::extensions.geometry) <> 'NaN'::float8
        AND extensions.st_y(search_point::extensions.geometry) <> 'NaN'::float8
        AND extensions.st_x(search_point::extensions.geometry) BETWEEN 80.0 AND 88.3
        AND extensions.st_y(search_point::extensions.geometry) BETWEEN 26.3 AND 30.5
        AND abs(
            extensions.st_x(search_point::extensions.geometry) * 100
            - round(extensions.st_x(search_point::extensions.geometry) * 100)
        ) < 0.000001
        AND abs(
            extensions.st_y(search_point::extensions.geometry) * 100
            - round(extensions.st_y(search_point::extensions.geometry) * 100)
        ) < 0.000001
    )
);

CREATE INDEX tenant_locations_current_point_gist
    ON app.tenant_locations USING gist (current_point);
CREATE INDEX tenant_locations_search_point_gist
    ON app.tenant_locations USING gist (search_point);

GRANT USAGE ON SCHEMA extensions TO rentra_api;

ALTER TABLE app.tenant_locations ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_locations_select_own ON app.tenant_locations
    FOR SELECT
    USING (user_id = nullif(current_setting('app.user_id', true), '')::uuid);

CREATE POLICY tenant_locations_insert_own ON app.tenant_locations
    FOR INSERT
    WITH CHECK (user_id = nullif(current_setting('app.user_id', true), '')::uuid);

CREATE POLICY tenant_locations_update_own ON app.tenant_locations
    FOR UPDATE
    USING (user_id = nullif(current_setting('app.user_id', true), '')::uuid)
    WITH CHECK (user_id = nullif(current_setting('app.user_id', true), '')::uuid);

REVOKE ALL ON app.tenant_locations FROM PUBLIC, anon, authenticated, rentra_api;
GRANT SELECT, INSERT, UPDATE ON app.tenant_locations TO rentra_api;
