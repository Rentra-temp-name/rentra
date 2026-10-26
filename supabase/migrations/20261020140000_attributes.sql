CREATE TABLE app.attributes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    key text NOT NULL UNIQUE,
    type text NOT NULL CHECK (type IN ('yes_no', 'single', 'multi')),
    pick_rule text NOT NULL CHECK (pick_rule IN ('yes_no', 'single', 'multi')),
    is_active boolean NOT NULL DEFAULT true,
    required_at_publish boolean NOT NULL DEFAULT false,
    CHECK (type = pick_rule)
);

ALTER TABLE app.attributes ENABLE ROW LEVEL SECURITY;

CREATE POLICY attributes_select_registry ON app.attributes
    FOR SELECT TO rentra_api
    USING (true);

REVOKE ALL ON app.attributes FROM PUBLIC, anon, authenticated, rentra_api;
GRANT SELECT ON app.attributes TO rentra_api;

INSERT INTO app.attributes (key, type, pick_rule, required_at_publish) VALUES
    ('tenant_type', 'multi', 'multi', true),
    ('pets', 'yes_no', 'yes_no', false),
    ('dietary', 'single', 'single', false),
    ('parties', 'single', 'single', false),
    ('smoking', 'single', 'single', false),
    ('alcohol', 'single', 'single', false),
    ('curfew', 'single', 'single', false),
    ('visitors', 'single', 'single', false),
    ('wall_decor', 'single', 'single', false),
    ('terrace_access', 'single', 'single', false),
    ('religious_events', 'single', 'single', false),
    ('floor_level', 'single', 'single', true),
    ('furnishing', 'single', 'single', true),
    ('property_type', 'single', 'single', true),
    ('road_type', 'single', 'single', true),
    ('separate_living_room', 'single', 'single', true),
    ('bathroom_attachment', 'single', 'single', true),
    ('pooja_room', 'yes_no', 'yes_no', true),
    ('study_room', 'yes_no', 'yes_no', true),
    ('private_rooftop_terrace', 'yes_no', 'yes_no', true),
    ('yard_garden', 'yes_no', 'yes_no', true),
    ('bike_parking', 'yes_no', 'yes_no', true),
    ('car_parking', 'yes_no', 'yes_no', true),
    ('ev_charging', 'yes_no', 'yes_no', true),
    ('water_supply', 'multi', 'multi', true),
    ('hot_water', 'single', 'single', true),
    ('backup_power', 'single', 'single', true),
    ('internet_fiber', 'yes_no', 'yes_no', true),
    ('cooling', 'multi', 'multi', true),
    ('laundry', 'multi', 'multi', true),
    ('kitchen_appliances', 'multi', 'multi', true),
    ('elevator', 'yes_no', 'yes_no', true),
    ('security', 'multi', 'multi', true),
    ('extras', 'multi', 'multi', true);
