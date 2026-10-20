CREATE FUNCTION app.get_public_profile(p_id uuid)
RETURNS TABLE (display_name text, whatsapp text)
LANGUAGE sql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
    SELECT profiles.display_name, profiles.whatsapp
    FROM profiles
    WHERE profiles.id = p_id
      AND profiles.deletion_requested_at IS NULL;
$$;

REVOKE ALL ON FUNCTION app.get_public_profile(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.get_public_profile(uuid) TO rentra_api;
