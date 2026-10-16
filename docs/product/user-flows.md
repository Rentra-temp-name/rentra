# User Flows and Page Structure

Status: partially decided. Items marked "Open" need a decision.

## Layout

- Public pages (landing, Rent, listing pages, About, Contact): top header.
- After login: the app switches to a sidebar layout, similar to MissLogger.
- Browsing is open to everyone. Login is required only for actions like save, preferences, and listing a property.

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

- **Home** with four sections:
  - For You: listings ranked by the tenant's preferences (matching)
  - Featured: boosted listings
  - Explore: listings shuffled once a day
  - Saved: favorited listings
- **Map** page
- Landlord items: My listings, Dashboard (shown to landlords)
- Account

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

- **Featured (boosted):** label kept as "boosted." How listings get boosted (paid or hand-picked) is not decided. Paid boosting depends on payments, which are Later in the MVP scope, so until that's decided, boosted listings are set by the team.
- **Explore:** decided. Listings are shuffled once a day.
- **For You before preferences:** decided. Visitors without preferences see a prompt to set their preferences in For You. Set-up flow for that prompt is open.
- **Landing map section:** decided. A static image the team designs and supplies, with a "View on map" button. Replaced by the live map once a provider is chosen.
