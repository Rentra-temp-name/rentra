# Rentra MVP Scope

Status: draft, pending review
Owner: Kritagya
Source: product doc (Rental App: Short Analysis) and decisions confirmed during planning

Rentra is a rental marketplace for Nepal, connecting tenants with landlords and property owners for apartments, hostels, and commercial spaces.

## In MVP

**Listings (landlord side)**
- Post, edit, pause, and delete listings
- Listings go live immediately when posted. No verification step for now.
- Seller dashboard with an overview of listing performance (views, inquiries)

**Discovery (tenant side)**
- Home feed of new and recommended listings
- Advanced filters
- Preference matching: tenants set preferences (for example pets, smoking) and get better matches
- Matching feels seamless: no waiting, no page reloads

**Map**
- Map search on a separate `/map` page, not part of the home feed
- The map provider is chosen later. The route is a placeholder for now.

**Favorites**
- Users can save listings for later

**Contact**
- Contact goes through WhatsApp links. No in-app chat in MVP.

**Accounts**
- Sign-in with Google through Supabase
- Two roles: tenant and landlord

## Later (not in MVP)

- Listing verification by a team member. To be revisited with the cofounder as the app grows.
- In-app chat
- Subscription plans for sellers
- Payments through a Nepal-based provider
- Tenant screening (background checks, rental history)
- Neighborhood analysis (road access, distance to main roads, schools, hospitals, population)
- Partner packages with service companies, such as cleaning agencies
- Mortgage and loan calculator
- Advanced analytics with demographics and matchmaking graphs

## Needs a decision

Listed in the product doc but not in its MVP list:
- Menu and utilities: profile, help, and FAQ pages
