CREATE TABLE app.numeric_fields (
    key text PRIMARY KEY,
    unit text NOT NULL,
    is_active boolean NOT NULL DEFAULT true
);

ALTER TABLE app.numeric_fields ENABLE ROW LEVEL SECURITY;

CREATE POLICY numeric_fields_select_registry ON app.numeric_fields
    FOR SELECT TO rentra_api
    USING (true);

REVOKE ALL ON app.numeric_fields FROM PUBLIC, anon, authenticated, rentra_api;
GRANT SELECT ON app.numeric_fields TO rentra_api;

INSERT INTO app.numeric_fields (key, unit) VALUES
    ('rent_amount', 'NPR per month'),
    ('bedrooms', 'count'),
    ('bathrooms_total', 'count'),
    ('western_commodes', 'count'),
    ('indian_squat_toilets', 'count'),
    ('kitchen_count', 'count'),
    ('balconies', 'count'),
    ('total_floors', 'count'),
    ('size_value', 'number'),
    ('max_people', 'count'),
    ('road_access_width_ft', 'feet'),
    ('main_road_distance_km', 'kilometers');
