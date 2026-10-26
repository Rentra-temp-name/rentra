# User Flows and Page Structure

Status: partially decided. Items marked "Open" need a decision.

## Layout

- Public pages (landing, Rent, listing pages, About, Contact): top header.
- After login: the app switches to a sidebar layout, similar to MissLogger.
- Browsing is open to everyone. Login is required only for actions like save, requirements, and listing a property.
- Tenant and landlord are switchable modes for a signed-in user, not stored roles. Switching modes keeps both sides' data.

## Public header

- Rent
- List a property (asks for login)
- About
- Contact
- Log in (or account menu when signed in)

## Landing page (public)

1. Hero with headline and search bar
2. Map section (responsive)
3. Listings preview, with "View all" linking to Rent
4. "Are you a landlord looking to enlist?" CTA
5. Footer

## App after login (sidebar)

- **Home** with three sections:
  - For You: perfect and ranked listings matched to the user's requirements, ranked by must fraction; perfect matches are uncapped, ranked results are capped at 100, and each miss is named. With no requirements, the user sees a daily explore feed and a nudge.
  - Explore: listings shuffled once a day
  - Saved: favorited listings
- **Notifications:** connection activity and changes to saved listings
- **Map** page
- Landlord items: My listings, Dashboard (shown to landlords)
- Account

Landlord listing states are draft, active, rented, sold_out, unavailable, and archived. Only active, unsuspended listings are public. Listing management is available to the owner through draft creation, versioned edits, publish, status changes, archive, restore before purge, and force-delete of archived listings. Jobs archive eligible inactive listings and purge archived listings after 30 days; suspended listings are locked from owner lifecycle changes and skipped by jobs. When editing answers or numeric details, the client submits the full replacement map.

Public detail and owner detail show the same position-ordered photo array. Owners can upload, delete, and reorder up to 10 photos; suspended and archived listings are locked for photo writes. Photos preserve their original aspect ratio, with fit-and-pad thumbnails.

Users can save or unsave listings. They can connect only to another user's public-visible listing; the tenant's WhatsApp is optional, and a saved number is shared with that listing's owner. The owner can view a connector's name and saved number through the connection profile; the connector can view the landlord's profile only while the landlord has a public-visible connected listing. Connection and saved-listing changes appear in the notifications sidebar; notifications have no phone numbers.

Users can report another user's listing. Admins review reports, resolve them with an optional audit note, and suspend or unsuspend listings. These actions are audited.

Clearing WhatsApp in the profile requires confirmation. Active, non-suspended listings are archived in the same transaction as the clear; if an active suspended listing exists, the clear is blocked. Direct database clears are also blocked while any listing is active. Restoring a listing that was active, and reactivating, require WhatsApp. `PUT /me` with a cleared WhatsApp first returns `WHATSAPP_CLEAR_ARCHIVES_LISTINGS` with the active non-suspended listing count; the client must then send `{confirm:true}` to archive those listings and clear the number.

## Page map

- `/` home (landing)
- `/rent` listings with filters and map toggle
- `/rent/[listing-slug]` single listing (public, indexable)
- `/map` map view
- `/list` landlord listing form (login required)
- `/saved` favorites (login required)
- `/app` app home after login (For You, Explore, Saved, Notifications)
- `/account` profile and landlord dashboard (login required)
- `/about`, `/contact` static pages

## Login

- Google sign-in through Supabase.
- Google One Tap: decided to use it. Timing (first visit or only on action) is open.

## Open

- **Explore:** decided. Listings are shuffled once a day.
- **For You before requirements:** users without requirements see a prompt to set them in For You. Set-up flow for that prompt is open.
- **Landing map section:** decided. A static image the team designs and supplies, with a "View on map" button. Replaced by the live map once a provider is chosen.
