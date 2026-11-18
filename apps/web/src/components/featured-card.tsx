import Link from "next/link";
import type { MainCardListing } from "@/components/main-card";

function listingHref(listing: MainCardListing) {
  const slug = listing.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  return `/rent/${slug || "home"}-${listing.id}`;
}

function formatRent(value?: string) {
  if (!value) return null;
  const amount = Number(value);
  return Number.isFinite(amount)
    ? `Rs. ${new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(amount)}/month`
    : `Rs. ${value}/month`;
}

function listingLocation(point?: MainCardListing["point"]) {
  if (!point || !Number.isFinite(point.latitude) || !Number.isFinite(point.longitude)) return null;
  const latitude = `${Math.abs(point.latitude).toFixed(3)}° ${point.latitude >= 0 ? "N" : "S"}`;
  const longitude = `${Math.abs(point.longitude).toFixed(3)}° ${point.longitude >= 0 ? "E" : "W"}`;
  return `${latitude} · ${longitude}`;
}

function FeaturedCardContent({ listing }: { listing: MainCardListing }) {
  const photo = listing.photos?.[0]?.original_url ?? "/rentra-cards/16862.png";
  const location = listing.location_label ?? listingLocation(listing.point);
  const rent = formatRent(listing.rent_amount ?? listing.rent);
  const hasBedrooms = listing.bedrooms !== undefined && listing.bedrooms !== "";
  const hasBathrooms = listing.bathrooms_total !== undefined && listing.bathrooms_total !== "";

  return (
    <>
      <img className="tenant-featured-image" src={photo} alt="" />
      <span className="tenant-featured-shade" />
      <span className="tenant-featured-details">
        <strong>{listing.title}</strong>
        {location ? <span className="tenant-featured-location">{location}</span> : null}
        {hasBedrooms || hasBathrooms ? (
          <span className="tenant-featured-specifications">
            {hasBedrooms ? `${listing.bedrooms} Bed` : null}
            {hasBedrooms && hasBathrooms ? <img src="/rentra-cards/e14fb.svg" alt="" /> : null}
            {hasBathrooms ? `${listing.bathrooms_total} Bath` : null}
          </span>
        ) : null}
        {rent ? <span>{rent}</span> : null}
      </span>
    </>
  );
}

export function FeaturedCard({ listing }: { listing: MainCardListing }) {
  return (
    <Link className="tenant-featured-property" href={listingHref(listing)} aria-label={`View featured property ${listing.title}`}>
      <FeaturedCardContent listing={listing} />
    </Link>
  );
}
