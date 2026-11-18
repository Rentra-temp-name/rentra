# Rentra Design System

Status: implementation reference for the current app UI; broader brand decisions still need input from Kritagya. Values below reflect the existing CSS tokens and implemented home/sidebar styles, not additional inferred brand rules.

## Colors

- Primary: `--color-primary` `#2275D8`
- Secondary: TBD
- Accent: TBD
- Background: `--color-background` `#F7F7F7`
- Surface: `--color-surface` `#FFFFFF`
- Text primary: `--color-text` `#2B2B2B`
- Text secondary: `--color-muted` `#7A7A7A`
- Success: TBD
- Error: `--color-error` `#D6453D`
- Warning: TBD

## Typography

- Font family (headings): IBM Plex Sans for the app home headings
- Font family (body): IBM Plex Sans (`--font-ui`)
- Type scale: Home greeting 32px/500; supporting text 16px/400; section headings 28px/500
- Line heights: Home greeting, supporting text, and section headings use 100%; letter spacing 0
- Font weights: Home heading 500; supporting text 400

## Spacing

- Base unit: TBD
- Scale: The home currently uses 10px between greeting and subtitle, 100px from welcome block to sections, 30px between section title/cards/Browse all, 150px between sections, and 50px between listing cards. These are page-specific values, not a global spacing scale.

## Radius and elevation

- Border radius: TBD
- Shadows: TBD

## Breakpoints

- Mobile: TBD
- Tablet: TBD
- Desktop: TBD

## Components

- Buttons (variants, sizes, states): TBD
- Inputs and form fields: TBD
- Cards (listing card, dashboard card): `MainCard` is reused for For You, New Listings, and Your Saved Listings.
  - Geometry: at most 372px wide; photo area 4:3 (279px tall at 372px wide), matching the API's 400×300 4:3 thumbnail. The photo uses `object-fit: cover`; matching ratios preserve the full padded thumbnail. The card has a 30px radius and `0 2px 7.5px rgba(104, 104, 104, .08)` shadow.
  - Spacing: body padding `20px 25px 20px 20px`, body/footer gap 20px, detail gap 10px, grid gap 50px, section content gap 30px, and section-to-section gap 150px. The 36×36 bookmark sits 10px from the card body's top and 11px from its right edge, so it follows the image height.
  - Type: title and rent use IBM Plex Sans 16px/500; location uses IBM Plex Sans 14px; specs use Segoe UI 14px/600; Active uses Inter 12px/500; posted age uses IBM Plex Sans 16px.
  - `FeaturedCard` is separate, at most 903px wide with a current 903:579 aspect ratio and a dark `rgba(34, 32, 32, .5)` overlay. This ratio is intentionally independent and may be changed later. Home Browse all links are below their section content and left aligned.
- Navigation and header: Persistent signed-in sidebar. Collapsed rail is 72px wide; 23px Lucide icon boxes have 24px horizontal margins and a 7px optical correction so the visible icons align with the centered `r` mark. Active icons use a filled treatment while inactive icons stay outlined. Home greeting is time-of-day plus the user's first name.
- Empty states and loading states: TBD
- Listing detail: the attached Figma Make screen is ported with its 1230px desktop content frame, 624.867×418 gallery, 30px photo radius, 30px summary gap, 100px section gaps, original IBM Plex Sans styles, handoff icons, amenity/requirement grids, map artwork, and CTA layout. The handoff sidebar is omitted; the existing `AppShell` sidebar remains. At narrower widths, the photo/summary columns stack.

## Motion

- Transitions and durations: TBD

## Rules

- Home colors use the existing background/text/muted/surface tokens above; no new palette is introduced for the dashboard.
- Featured card is 903×579px on desktop, with details inset 65px from the left and bottom. Browse all sits below each section's cards and is left aligned.
