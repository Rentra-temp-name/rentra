# Data Model

Status: draft. Field lists come from decisions so far and will change.

## profiles
One row per user, linked to Supabase Auth.
- id (matches auth user id)
- role: tenant or landlord
- full name
- created_at

## listings
- id
- landlord_id (references profiles)
- title
- rent
- deposit
- bedrooms
- bathrooms
- furnished (yes or no)
- pets allowed (yes or no)
- area (text)
- description
- landlord WhatsApp number
- landlord phone number
- photos (stored in Supabase Storage, referenced here)
- status: active, paused, or rented
- boosted (yes or no)
- created_at, updated_at

Listings are published immediately on creation. No verification step in V1.

## tenant_preferences
- user_id (references profiles)
- budget minimum and maximum
- bedrooms minimum
- furnished (any, yes, or no)
- pets (yes or no)
- preferred areas
- other preferences, to be defined from the product doc

## favorites
- user_id (references profiles)
- listing_id (references listings)
- created_at
- Unique on (user_id, listing_id)

## Not defined yet

- Location coordinates: needed for the map, which is deferred.
- Landlord constraints (who a landlord will accept).
- Preference fields beyond those listed above.
