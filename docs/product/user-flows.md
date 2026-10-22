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
  - For You: listings matched to the user's requirements
  - Explore: listings shuffled once a day
  - Saved: favorited listings
- **Map** page
- Landlord items: My listings, Dashboard (shown to landlords)
- Account

Landlord listing states are draft, active, rented, sold_out, unavailable, and archived. Only active, unsuspended listings are public. Listing management is available to the owner through draft creation, versioned edits, and publish, status, archive, restore, and force-delete actions. When editing answers or numeric details, the client submits the full replacement map.

Clearing WhatsApp in the profile requires confirmation. Active, non-suspended listings are archived as part of the clear; if an active suspended listing exists, the clear is blocked. Restoring a listing that was active, and reactivating, require WhatsApp.

## Page map

- `/` home (landing)
- `/rent` listings with filters and map toggle
- `/rent/[listing-slug]` single listing (public, indexable)
- `/map` map view
- `/list` landlord listing form (login required)
- `/saved` favorites (login required)
- `/app` app home after login (For You, Featured, Explore, Saved)
- `/account` profile and landlord dashboard (login required)
- `/about`, `/contact` static pages

## Login

- Google sign-in through Supabase.
- Google One Tap: decided to use it. Timing (first visit or only on action) is open.

## Open

- **Explore:** decided. Listings are shuffled once a day.
- **For You before requirements:** users without requirements see a prompt to set them in For You. Set-up flow for that prompt is open.
- **Landing map section:** decided. A static image the team designs and supplies, with a "View on map" button. Replaced by the live map once a provider is chosen.
