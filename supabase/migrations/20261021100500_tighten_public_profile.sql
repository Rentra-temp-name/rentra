CREATE OR REPLACE FUNCTION app.get_public_profile(p_id uuid)
RETURNS TABLE (display_name text, whatsapp text)
LANGUAGE sql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
    SELECT profile.display_name, profile.whatsapp
    FROM app.profiles AS profile
    WHERE profile.id = p_id
      AND profile.deletion_requested_at IS NULL
      AND EXISTS (
          SELECT 1
          FROM app.listings AS listing
          WHERE listing.owner_id = profile.id
            AND listing.status = 'active'
            AND listing.suspended_at IS NULL
      );
$$;

REVOKE ALL ON FUNCTION app.get_public_profile(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.get_public_profile(uuid) TO rentra_api;
