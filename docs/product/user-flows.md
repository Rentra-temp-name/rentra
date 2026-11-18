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

## App after login (persistent sidebar)

The signed-in app keeps the sidebar shell across app pages. Its collapsed state is an icon-only rail; the active page uses the filled treatment for that icon while inactive icons remain outlined. The sidebar also contains Notifications and Account.

- **Home** greets the tenant by first name with a time-of-day greeting and shows:
  - **For You:** fetched from the backend `GET /matches` endpoint. The backend applies eligibility, requirements, scoring, and ordering; the home preserves the returned order, takes up to six cards, and does not score or re-rank in the frontend. Perfect matches are uncapped in the backend, ranked results are capped at 100, and ranked results include named misses. With no requirements, the backend returns its daily explore feed. Preview cards are shown only when no listings are available to render. See [the matching contract](../rentra-v1-backend-handoff.md#5-matching).
  - **Featured:** a wide highlighted rental rendered by `FeaturedCard`, with its own image ratio and dark overlay. It currently reuses API-loaded For You/New Listings candidates; the selection rule still needs a real featured-listing source because the current database/API has no `is_featured` field.
  - **New Listings:** recent rentals with a Browse all link below the cards.
  - **Your Saved Listings:** saved rentals with a Browse all link below the cards.
- **MainCard:** one shared listing-card component is used in For You, New Listings, and Your Saved Listings. Its full surface opens `/rent/[listing-slug]`; the bookmark remains a separate save action. It displays the listing title, rent, point-derived location, bedroom count, bathroom count, size in square feet, first photo, and creation date. The photo area is 4:3 to match the API thumbnail ratio; the card's typography, shadow, padding, and spacing are specified in the design system. Preview data is only for layout testing and should not replace real listing data after setup.
- **Explore:** listings shuffled once a day.
- **Saved:** favorited listings.
- **Notifications:** connection activity and changes to saved listings.
- **Map** page.
- Landlord items: My listings and Dashboard (shown to landlords).
- **Account.**

Landlord listing states are draft, active, rented, sold_out, unavailable, and archived. Only active, unsuspended listings are public. Listing management is available to the owner through draft creation, versioned edits, publish, status changes, archive, restore before purge, and force-delete of archived listings. Jobs archive eligible inactive listings and purge archived listings after 30 days; suspended listings are locked from owner lifecycle changes and skipped by jobs. When editing answers or numeric details, the client submits the full replacement map.

Public detail and owner detail show the same position-ordered photo array. Owners can upload, delete, and reorder up to 10 photos; suspended and archived listings are locked for photo writes. Photos preserve their original aspect ratio, with fit-and-pad thumbnails.

The listing detail route is `/rent/[listing-slug]` and stays inside the existing persistent app sidebar. It ports the attached Figma screen and fetches public `GET /listings/{id}`, accepting the card URL whose final segment is the listing UUID. The title, rent, bedroom/bathroom/size values, first ordered photo, creation age, public landlord display name, and contact actions use the listing response. The API also returns selected `answers`; the Amenities and Requirements tiles currently retain the handoff's sample content and still need binding to those answers. The map artwork and Neighborhood examples are also handoff placeholders. A named location and descriptive prose are not currently stored in the listing schema. The handoff's “Match” labels need a user-specific detail match API; the page must not infer a match from a listing answer alone.

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
- `/app` app home after login (For You, Featured, New Listings, Saved Listings)
- `/account` profile and landlord dashboard (login required)
- `/about`, `/contact` static pages

## Login

- Google sign-in through Supabase.
- Google One Tap: decided to use it. Timing (first visit or only on action) is open.

## Open

- **Explore:** decided. Listings are shuffled once a day.
- **For You before requirements:** users without requirements see a prompt to set them in For You. Set-up flow for that prompt is open.
- **Landing map section:** decided. A static image the team designs and supplies, with a "View on map" button. Replaced by the live map once a provider is chosen.
