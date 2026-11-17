alter table app.profiles
  add column if not exists active_role text;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'app.profiles'::regclass
      and conname = 'profiles_active_role_check'
  ) then
    alter table app.profiles
      add constraint profiles_active_role_check
      check (active_role is null or active_role in ('tenant', 'landlord'));
  end if;
end $$;

grant select (active_role), insert (active_role), update (active_role)
  on app.profiles to rentra_api;

comment on column app.profiles.active_role is
  'UI mode only (tenant or landlord). NULL means first-time user, show role onboarding. Never use for authorization.';
