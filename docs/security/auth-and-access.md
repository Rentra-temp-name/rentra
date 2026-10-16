# Auth and Access

Status: draft.

## Sign-in

- Google sign-in through Supabase Auth.
- Google One Tap is used. Timing is open (see user-flows.md).
- Browsing does not require login.

## Roles

- **Visitor:** not signed in
- **Tenant:** signed in, can save listings and set preferences
- **Landlord:** signed in, can create and manage their own listings

No admin role in V1. Launch listings are entered through landlord accounts, or directly by the team through the Supabase dashboard.

## Access rules

| Action | Visitor | Tenant | Landlord |
|---|---|---|---|
| Browse and search active listings | Yes | Yes | Yes |
| View listing details | Yes | Yes | Yes |
| See landlord WhatsApp and phone on a listing | Yes | Yes | Yes |
| Save listings | No | Yes | Yes |
| Set and edit own preferences | No | Yes | Yes |
| Create listings | No | No | Yes |
| Edit, pause, or delete own listings | No | No | Yes |
| View overview of own listings | No | No | Yes |
| Edit another user's listing or data | No | No | No |

## Contact details

- Landlord WhatsApp number and phone number are shown on each listing.
- Visible to everyone, including visitors. Decided.

## Data protection

- Row Level Security is enabled on every table.
- Each rule is tested in `supabase/tests`.
- Secrets are never stored in the repo or the browser.
