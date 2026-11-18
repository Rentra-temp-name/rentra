# Things to Do After Setting Everything Up

## Purpose

Use this checklist after the real Supabase project, API, Storage bucket, and frontend environment are connected, and separate real tenant and landlord accounts are available. The goal is to verify that a landlord's published listing reaches the tenant's home through backend matching, with the existing card design intact.

## Home components and what needs wiring

| Component or data source | Current state | After setup |
| --- | --- | --- |
| `TenantHome` (`apps/web/src/components/tenant-home.tsx`) | Requests `/matches?page_size=6`, `/listings?page_size=6`, and `/me/saved?page_size=6`. It displays at most six For You cards; under requirements the matches API can return all perfect matches plus up to 100 ranked matches, while `page_size` limits the no-requirements explore feed. | Verify these requests with the live API and real user accounts; keep matching/ranking in the backend. |
| `MainCard` (`apps/web/src/components/main-card.tsx`) | Built as the shared listing card used by For You, New Listings, and Your Saved Listings. The full card opens the detail route; the bookmark stays a separate save action. Its CSS supplies the typography, image treatment, shadow, padding, bookmark position, and spacing. | Keep and populate it with API listing data. Do not recreate the card separately for each section. If its design changes, update this shared component and its shared CSS. |
| `ListingSection` in `tenant-home.tsx` | Renders the three home sections, loading skeletons, empty states, and Browse all links. It currently substitutes preview cards when a section has no rows. | Keep the section layout. Once real accounts/data are ready, verify each section from its API source and remove the synthetic preview records before production. |
| `previewListings()` and `featuredPreview` in `tenant-home.tsx` | Hard-coded layout-testing data and local image paths. | Replace with real returned rows or honest empty states; never let these values be mistaken for landlord listings. |
| `getCardDetails()` in `tenant-home.tsx` | Hydrates the summary rows with `GET /listings/{id}` to get numeric values and ordered photos. If this detail request fails, it currently silently falls back to the summary row, which may lack numeric values or photos. | Confirm that the live API response includes the fields below and that hydration succeeds for For You, New Listings, and Saved. Before launch, decide whether detail failures should show a retry/error state instead of a partial card. Consider a combined response later if per-card detail requests become a performance issue. |
| `FeaturedSection` in `tenant-home.tsx` | Owns the Featured heading, slide selection/dots, loading state, and Browse all link. It chooses from the already API-loaded For You and New Listings rows, preferring `is_featured` and otherwise falling back to available rows. | Keep section/carousel behavior separate from card presentation. Choose a true featured-listing source before launch; the database/API currently has no `is_featured` field or featured-selection endpoint. |
| `FeaturedCard` (`apps/web/src/components/featured-card.tsx`) | Reusable wide-card presentation. Receives one selected listing from `FeaturedSection`; it makes no API call itself and renders only title, point-derived location, bedroom/bathroom counts, rent, and the first image. | Keep it wired to the selected API-fed listing. It has its own independent image ratio and dark overlay; tune its ratio later without changing `MainCard`. |
| Listing detail (`apps/web/src/components/listing-detail.tsx`, `figma-listing-detail.tsx`) | Ports the attached Figma layout inside the persistent `AppShell`. Real listing title, rent, bedrooms, bathrooms, size, first photo, creation age, landlord display name, and contact actions load from `GET /listings/{id}`. Synthetic home-card IDs use local preview data. | Verify those API-bound fields with a published real listing. Bind the Amenities and Requirements tiles to the endpoint's `answers` before treating their current Figma sample labels as listing data. Replace the handoff map artwork/nearby examples with location-backed content when available. The schema has no description or named locality; “Match” badges need a user-specific detail match contract. |
| `ListingSkeleton` in `tenant-home.tsx` | Loading placeholder for regular cards. | Keep its 4:3 photo shape aligned with `MainCard`. |

## For You matching and API flow

1. `TenantHome` requests `GET /matches?page_size=6` with the signed-in tenant's access token. This request reaches FastAPI; the browser does not query Supabase or calculate match scores.
2. The backend applies the matching contract in [handoff section 5](rentra-v1-backend-handoff.md#5-matching): only active, unsuspended, non-owner listings inside the tenant's saved search radius are eligible. It evaluates the tenant's current must/nice requirements and returns `{perfect, ranked: [{listing, misses}], explore, nudge, explore_listings, next_cursor}`. Without requirements, the rows are the daily `explore_listings` feed.
3. Preserve the backend's order: perfect listings first in returned order, followed by each ranked item's `listing` in returned order; use `explore_listings` for the no-requirements explore response. Do not re-score or sort these results in the frontend. The current home deduplicates by listing ID and shows at most six cards. The backend's perfect matches are uncapped and ranked matches are capped at 100, but this home preview still renders only six.
4. For each visible match, `getCardDetails()` calls `GET /listings/{id}` to hydrate `numeric` values and ordered photo URLs. The client maps `numeric.bedrooms`, `numeric.bathrooms_total`, and `numeric.size_value` to the card's display fields.
5. `MainCard` only formats and displays the returned listing. It must not decide eligibility, calculate scores, or reorder the results. Backend miss reasons remain part of the match response but are not currently displayed on the home card. The home currently ignores `nudge` and `next_cursor`; if the no-requirements prompt or additional pages are wired later, use those response fields and keep backend ordering.

New Listings and Saved use their own list endpoints, then the same detail hydration and `MainCard`; they do not run tenant matching. Featured currently reuses the API-loaded For You/New Listings candidates, so there is no separate Featured request. `FeaturedCard` reads only the fields it presents from the selected candidate. If Featured later needs independent selection, add a deliberate backend source/API contract rather than making the card query Supabase or picking arbitrary records.

## MainCard data mapping

The component should display values from the landlord's listing record and its linked records:

| Card display | API/database source |
| --- | --- |
| Title | `listings.title` / API `title` |
| Rent | `listings.rent_amount` / API `rent_amount` (NPR per month) |
| Bedrooms | `listing_numeric` row with field `bedrooms`, returned in API `numeric.bedrooms` |
| Bathrooms | `listing_numeric` row with field `bathrooms_total`, returned in API `numeric.bathrooms_total` |
| Size | `listing_numeric` row with field `size_value`, returned in API `numeric.size_value`; input and display are square feet only |
| Location | `listings.point` / API `point`; the current card formats the coordinates for display. A named neighborhood is not currently stored or returned. |
| Created date | `listings.created_at` / API `created_at`; the card formats it as a posted-age label |
| Photo | First position-ordered `listing_photos` item from API `photos`; use its `thumb_url`, with `original_url` as fallback |

The card also uses listing ID for its detail link and the saved-listings response for the bookmark state. Public listing endpoints already filter to active, unsuspended listings, so the card's Active indicator follows that visibility rule.

## Verify with real tenant and landlord accounts

1. Finish real Supabase setup from the [backend handoff](rentra-v1-backend-handoff.md): apply migrations, configure the `rentra_api` pooler credentials, create the public `listing-photos` bucket, configure Google OAuth, and set the API and web environment variables.
2. Create two separate accounts: one landlord account and one tenant account. The tenant and landlord modes on one profile are UI modes; matching should be checked across different users because users do not match their own listings.
3. As the landlord, set the required profile contact information, create a listing, enter its title, rent, point, bedroom count, bathroom count, and size in square feet, upload a photo, complete required answers, and publish it.
4. Check `GET /listings/{id}` for the published listing. Confirm `title`, `rent_amount`, `point`, `created_at`, `numeric.bedrooms`, `numeric.bathrooms_total`, `numeric.size_value`, ordered `photos`, and `answers` agree with the landlord's entries. Open the listing card and check its detail page contact actions and visible fields against the same response.
5. As the tenant, save a search point/radius and requirements that the test listing satisfies. Check `GET /matches` and verify the backend's eligible IDs and order. Then confirm For You keeps that order, shows at most six cards, and `MainCard` displays the actual values and image.
6. Check New Listings, save the listing, and confirm it appears in Your Saved Listings. Verify that removing the save removes it from that section.
7. Check a no-match tenant and an empty saved list. Confirm the production empty-state decision and that test preview data is not shown as a real listing.
8. Decide and verify the Featured selection rule separately; it is not currently represented in the database.

## Locked card geometry

- Regular card width: at most 372px.
- Photo area: 4:3; 279px tall at 372px width. The loading skeleton uses the same ratio.
- The API makes 400×300 4:3 fit-and-pad thumbnails. The card displays the thumbnail in the matching 4:3 area.
- Existing card radius, shadow, fonts, internal padding, bookmark placement, 50px card gap, 30px section content gap, and 150px section gap are recorded in the [design system](design-system/README.md).
- `MainCard` is a shared component: maintain the styling in one place so a design adjustment applies consistently across all three listing sections.
- `FeaturedCard` has its own current 903:579 image ratio and dark overlay; both are independent of `MainCard` and may be tuned later.
