CREATE FUNCTION app.map_points(
    p_west float8,
    p_south float8,
    p_east float8,
    p_north float8,
    p_limit int
)
RETURNS TABLE (id uuid, lat float8, lng float8, rent_amount numeric)
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = app, extensions, pg_temp
AS $$
    SELECT l.id,
           extensions.st_y(l.point::extensions.geometry),
           extensions.st_x(l.point::extensions.geometry),
           l.rent_amount
    FROM app.listings AS l
    WHERE l.status = 'active'
      AND l.suspended_at IS NULL
      AND extensions.st_intersects(
          l.point,
          extensions.st_makeenvelope(p_west, p_south, p_east, p_north, 4326)::extensions.geography
      )
    ORDER BY l.rent_amount, l.id
    LIMIT p_limit;
$$;

CREATE FUNCTION app.map_clusters(
    p_west float8,
    p_south float8,
    p_east float8,
    p_north float8,
    p_eps float8,
    p_limit int
)
RETURNS TABLE (cnt int, lat float8, lng float8)
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = app, extensions, pg_temp
AS $$
    WITH visible AS (
        SELECT l.id, l.rent_amount, l.point::extensions.geometry AS geom
        FROM app.listings AS l
        WHERE l.status = 'active'
          AND l.suspended_at IS NULL
          AND extensions.st_intersects(
              l.point,
              extensions.st_makeenvelope(p_west, p_south, p_east, p_north, 4326)::extensions.geography
          )
    ), clustered AS (
        SELECT extensions.st_clusterdbscan(geom, p_eps, 1) OVER () AS cluster_id,
               geom
        FROM visible
    )
    SELECT count(*)::integer,
           extensions.st_y(extensions.st_centroid(extensions.st_collect(geom))),
           extensions.st_x(extensions.st_centroid(extensions.st_collect(geom)))
    FROM clustered
    GROUP BY cluster_id
    ORDER BY cluster_id
    LIMIT p_limit;
$$;

REVOKE ALL ON FUNCTION app.map_points(float8, float8, float8, float8, int) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.map_clusters(float8, float8, float8, float8, float8, int) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.map_points(float8, float8, float8, float8, int) TO rentra_api;
GRANT EXECUTE ON FUNCTION app.map_clusters(float8, float8, float8, float8, float8, int) TO rentra_api;
