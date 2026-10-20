-- Schema app: internal backend schema, isolated from Data API
CREATE SCHEMA IF NOT EXISTS app;

-- Revoke all privileges on schema app from PUBLIC, anon, and authenticated
REVOKE ALL ON SCHEMA app FROM PUBLIC;
REVOKE ALL ON SCHEMA app FROM anon;
REVOKE ALL ON SCHEMA app FROM authenticated;

-- Role rentra_api: application runtime role with minimal privileges
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rentra_api') THEN
        CREATE ROLE rentra_api WITH LOGIN NOINHERIT NOBYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE;
    ELSE
        ALTER ROLE rentra_api WITH LOGIN NOINHERIT NOBYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END
$$;

-- Grant USAGE on schema app only to rentra_api; ensure no CREATE and no ownership
GRANT USAGE ON SCHEMA app TO rentra_api;
REVOKE CREATE ON SCHEMA app FROM rentra_api;

-- Alter default privileges in schema app so new tables, sequences, and functions never grant to anon or authenticated
ALTER DEFAULT PRIVILEGES IN SCHEMA app REVOKE ALL ON TABLES FROM anon, authenticated, PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA app REVOKE ALL ON SEQUENCES FROM anon, authenticated, PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA app REVOKE ALL ON FUNCTIONS FROM anon, authenticated, PUBLIC;
