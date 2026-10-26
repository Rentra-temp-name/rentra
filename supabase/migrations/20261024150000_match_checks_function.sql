CREATE FUNCTION app.match_checks(p_uid uuid, p_lng float8, p_lat float8, p_radius_m float8)
RETURNS TABLE (
    id uuid,
    owner_id uuid,
    title text,
    rent_amount numeric,
    created_at timestamptz,
    lat float8,
    lng float8,
    must_miss bigint,
    nice_miss bigint,
    must_total bigint,
    nice_total bigint,
    misses jsonb
)
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
SET search_path = app, extensions, pg_temp
AS $$
BEGIN
    IF p_uid IS DISTINCT FROM nullif(current_setting('app.user_id', true), '')::uuid THEN
        RAISE EXCEPTION 'MATCH_USER_MISMATCH' USING ERRCODE = '42501';
    END IF;

    RETURN QUERY
    SELECT l.id, l.owner_id, l.title, l.rent_amount, l.created_at,
        extensions.st_y(l.point::extensions.geometry)::float8,
        extensions.st_x(l.point::extensions.geometry)::float8,
        count(*) FILTER (WHERE r.importance = 'must' AND miss),
        count(*) FILTER (WHERE r.importance = 'nice' AND miss),
        count(*) FILTER (WHERE r.importance = 'must'),
        count(*) FILTER (WHERE r.importance = 'nice'),
        coalesce(
            jsonb_agg(jsonb_build_object('field', r.label, 'value', r.expected, 'importance', r.importance))
                FILTER (WHERE miss),
            '[]'::jsonb
        )
    FROM app.listings l
    LEFT JOIN LATERAL (
        SELECT r.importance, coalesce(a.key, n.field) AS label, coalesce(o.label, n.field) AS expected,
            CASE WHEN n.field IS NOT NULL THEN
                CASE n.field WHEN 'rent_amount' THEN l.rent_amount > n.value
                    ELSE coalesce((
                        SELECT ln.value FROM app.listing_numeric ln
                        WHERE ln.listing_id = l.id AND ln.field = r.field
                    ), 0) < n.value
                END
            ELSE NOT EXISTS (
                SELECT 1 FROM app.listing_answers la
                WHERE la.listing_id = l.id AND la.attribute_id = r.attribute_id AND la.option_id = r.option_id
            ) AND NOT EXISTS (
                SELECT 1 FROM app.listing_answers la
                JOIN app.attribute_options ao ON ao.id = la.option_id
                WHERE la.listing_id = l.id AND la.attribute_id = r.attribute_id AND ao.is_exclusive
            )
            END AS miss
        FROM (
            SELECT user_id, attribute_id, option_id, pick_rule, importance, NULL::text AS field
            FROM app.requirements WHERE user_id = p_uid
            UNION ALL
            SELECT user_id, NULL, NULL, NULL, importance, field
            FROM app.requirement_numeric WHERE user_id = p_uid
        ) r
        LEFT JOIN app.attributes a ON a.id = r.attribute_id
        LEFT JOIN app.attribute_options o ON o.id = r.option_id
        LEFT JOIN app.requirement_numeric n ON n.user_id = r.user_id AND n.field = r.field
    ) r ON true
    WHERE l.status = 'active' AND l.suspended_at IS NULL AND l.owner_id <> p_uid
      AND extensions.st_dwithin(
          l.point,
          extensions.st_setsrid(extensions.st_makepoint(p_lng, p_lat), 4326)::extensions.geography,
          p_radius_m
      )
    GROUP BY l.id;
END;
$$;

REVOKE ALL ON FUNCTION app.match_checks(uuid, float8, float8, float8) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.match_checks(uuid, float8, float8, float8) TO rentra_api;
