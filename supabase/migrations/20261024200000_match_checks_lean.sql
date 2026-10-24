DROP FUNCTION app.match_checks(uuid, float8, float8, float8);

CREATE FUNCTION app.match_checks(p_uid uuid, p_lng float8, p_lat float8, p_radius_m float8)
RETURNS TABLE (
    id uuid, owner_id uuid, title text, rent_amount numeric, created_at timestamptz,
    lat float8, lng float8, must_miss bigint, nice_miss bigint,
    must_total bigint, nice_total bigint, misses jsonb, distance_m float8
)
LANGUAGE plpgsql SECURITY DEFINER STABLE
SET search_path = app, extensions, pg_temp
AS $$
BEGIN
    IF p_uid IS DISTINCT FROM nullif(current_setting('app.user_id', true), '')::uuid THEN
        RAISE EXCEPTION 'MATCH_USER_MISMATCH' USING ERRCODE = '42501';
    END IF;

    RETURN QUERY
    WITH req AS MATERIALIZED (
        SELECT r.attribute_id, r.option_id, r.importance FROM app.requirements r WHERE r.user_id = p_uid
    ), num_req AS MATERIALIZED (
        SELECT r.field, r.value, r.importance FROM app.requirement_numeric r WHERE r.user_id = p_uid
    ), eligible AS MATERIALIZED (
        SELECT l.id, l.owner_id, l.title, l.rent_amount, l.created_at,
               extensions.st_y(l.point::extensions.geometry)::float8 AS lat,
               extensions.st_x(l.point::extensions.geometry)::float8 AS lng,
               extensions.st_distance(l.point, extensions.st_setsrid(extensions.st_makepoint(p_lng,p_lat),4326)::extensions.geography,false)::float8 AS distance_m
        FROM app.listings l
        WHERE l.status='active' AND l.suspended_at IS NULL AND l.owner_id <> p_uid
          AND extensions.st_dwithin(l.point, extensions.st_setsrid(extensions.st_makepoint(p_lng,p_lat),4326)::extensions.geography,p_radius_m)
    ), attr_satisfied AS (
        SELECT attr_rows.id, attr_rows.importance, count(*)::bigint AS satisfied
        FROM (
            SELECT e.id, r.attribute_id, r.option_id, r.importance
            FROM req r
            JOIN app.listing_answers a
              ON a.attribute_id=r.attribute_id AND a.option_id=r.option_id
            JOIN eligible e ON e.id=a.listing_id
            UNION ALL
            SELECT DISTINCT e.id, r.attribute_id, r.option_id, r.importance
            FROM req r
            JOIN app.listing_answers a ON a.attribute_id=r.attribute_id
            JOIN app.attribute_options o ON o.id=a.option_id AND o.is_exclusive
            JOIN eligible e ON e.id=a.listing_id
            WHERE NOT EXISTS (
                SELECT 1
                FROM app.listing_answers a2
                WHERE a2.listing_id=e.id
                  AND a2.attribute_id=r.attribute_id
                  AND a2.option_id=r.option_id
            )
        ) attr_rows
        GROUP BY attr_rows.id, attr_rows.importance
    ), ln AS MATERIALIZED (
        SELECT n.listing_id, n.field, n.value
        FROM app.listing_numeric n
        JOIN eligible e ON e.id=n.listing_id
        WHERE n.field IN (
            SELECT nr.field FROM num_req nr WHERE nr.field<>'rent_amount'
        )
    ), num_satisfied AS (
        SELECT e.id, r.importance, count(*)::bigint AS satisfied
        FROM eligible e JOIN num_req r
          ON r.field='rent_amount' AND e.rent_amount <= r.value
        GROUP BY e.id, r.importance
        UNION ALL
        SELECT ln.listing_id, r.importance, count(*)::bigint AS satisfied
        FROM ln JOIN num_req r ON r.field=ln.field AND ln.value>=r.value
        GROUP BY ln.listing_id, r.importance
        UNION ALL
        SELECT e.id, r.importance, count(*)::bigint AS satisfied
        FROM eligible e CROSS JOIN num_req r
        WHERE r.field<>'rent_amount' AND r.value<=0
          AND NOT EXISTS (
              SELECT 1 FROM ln
              WHERE ln.listing_id=e.id AND ln.field=r.field
          )
        GROUP BY e.id, r.importance
    ), sat AS (
        SELECT satisfied_rows.id,
               sum(satisfied) FILTER (WHERE importance='must')::bigint AS must_sat,
               sum(satisfied) FILTER (WHERE importance='nice')::bigint AS nice_sat
        FROM (SELECT * FROM attr_satisfied UNION ALL SELECT * FROM num_satisfied) satisfied_rows
        GROUP BY satisfied_rows.id
    ), totals AS (
        SELECT count(*) FILTER(WHERE importance='must')::bigint AS must_total,
               count(*) FILTER(WHERE importance='nice')::bigint AS nice_total FROM (SELECT importance FROM req UNION ALL SELECT importance FROM num_req) q
    )
    SELECT e.id,e.owner_id,e.title,e.rent_amount,e.created_at,e.lat,e.lng,
           t.must_total-coalesce(s.must_sat,0),
           t.nice_total-coalesce(s.nice_sat,0),
           t.must_total,t.nice_total,'[]'::jsonb,e.distance_m
    FROM eligible e CROSS JOIN totals t LEFT JOIN sat s ON s.id=e.id;
END;
$$;
REVOKE ALL ON FUNCTION app.match_checks(uuid, float8, float8, float8) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.match_checks(uuid, float8, float8, float8) TO rentra_api;

CREATE FUNCTION app.match_misses(p_uid uuid, p_listing_ids uuid[])
RETURNS TABLE (listing_id uuid, misses jsonb)
LANGUAGE plpgsql SECURITY DEFINER STABLE
SET search_path = app, extensions, pg_temp
AS $$
BEGIN
    IF p_uid IS DISTINCT FROM nullif(current_setting('app.user_id', true), '')::uuid THEN
        RAISE EXCEPTION 'MATCH_USER_MISMATCH' USING ERRCODE = '42501';
    END IF;
    RETURN QUERY
    WITH req AS (
        SELECT r.importance,a.key::text AS field,o.label::text AS value,r.attribute_id,r.option_id,NULL::text AS numeric_field,NULL::numeric AS numeric_value
        FROM app.requirements r JOIN app.attributes a ON a.id=r.attribute_id JOIN app.attribute_options o ON o.id=r.option_id WHERE r.user_id=p_uid
        UNION ALL
        SELECT r.importance,r.field,r.field,NULL::uuid,NULL::uuid,r.field,r.value FROM app.requirement_numeric r WHERE r.user_id=p_uid
    ), missed AS (
        SELECT ids.id AS listing_id,r.field,r.value,r.importance
        FROM unnest(coalesce(p_listing_ids,'{}'::uuid[])) ids(id) JOIN app.listings l ON l.id=ids.id
        JOIN req r ON true
        LEFT JOIN app.listing_numeric n ON n.listing_id=l.id AND n.field=r.numeric_field
        WHERE (r.attribute_id IS NOT NULL AND NOT EXISTS (
                   SELECT 1 FROM app.listing_answers a
                   JOIN app.attribute_options ao ON ao.id=a.option_id
                   WHERE a.listing_id=l.id AND a.attribute_id=r.attribute_id
                     AND (a.option_id=r.option_id OR ao.is_exclusive)
               ))
           OR (r.numeric_field='rent_amount' AND l.rent_amount>r.numeric_value)
           OR (r.numeric_field IS NOT NULL AND r.numeric_field<>'rent_amount' AND coalesce(n.value,0)<r.numeric_value)
    )
    SELECT m.listing_id,coalesce(jsonb_agg(jsonb_build_object('field',m.field,'value',m.value,'importance',m.importance)),'[]'::jsonb)
    FROM missed m GROUP BY m.listing_id;
END;
$$;
REVOKE ALL ON FUNCTION app.match_misses(uuid, uuid[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.match_misses(uuid, uuid[]) TO rentra_api;
