"use client";

import Link from "next/link";

type Point = { latitude: number; longitude: number };
type ListingPhoto = { original_url?: string; thumb_url?: string };

export type MainCardListing = {
  id: string;
  title: string;
  location_label?: string;
  bedrooms?: number | string;
  bathrooms_total?: number | string;
  size_value?: number | string;
  rent_amount?: string;
  rent?: string;
  numeric?: Record<string, string>;
  point?: Point;
  photos?: ListingPhoto[];
  created_at?: string;
  visible?: boolean;
  is_featured?: boolean;
  is_preview?: boolean;
};

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

function listingLocation(point?: Point) {
  if (!point || !Number.isFinite(point.latitude) || !Number.isFinite(point.longitude)) return null;
  const latitude = `${Math.abs(point.latitude).toFixed(3)}° ${point.latitude >= 0 ? "N" : "S"}`;
  const longitude = `${Math.abs(point.longitude).toFixed(3)}° ${point.longitude >= 0 ? "E" : "W"}`;
  return `${latitude} · ${longitude}`;
}

function postedAge(createdAt?: string) {
  if (!createdAt) return null;
  const elapsed = Math.max(0, Date.now() - new Date(createdAt).getTime());
  if (!Number.isFinite(elapsed)) return null;
  const days = Math.floor(elapsed / 86_400_000);
  if (!days) return "Today";
  if (days === 1) return "1 day ago";
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30);
  return months === 1 ? "1 month ago" : `${months} months ago`;
}

export function MainCard({
  listing,
  saved,
  saving,
  onToggleSaved,
}: {
  listing: MainCardListing;
  saved: boolean;
  saving: boolean;
  onToggleSaved: () => void;
}) {
  const photo = listing.photos?.[0]?.thumb_url ?? listing.photos?.[0]?.original_url;
  const location = listing.location_label ?? listingLocation(listing.point);
  const rent = formatRent(listing.rent_amount ?? listing.rent);
  const age = postedAge(listing.created_at);
  const specifications = [
    listing.bedrooms !== undefined && listing.bedrooms !== "" ? `${listing.bedrooms} Bed` : null,
    listing.bathrooms_total !== undefined && listing.bathrooms_total !== "" ? `${listing.bathrooms_total} Bath` : null,
    listing.size_value !== undefined && listing.size_value !== "" ? `${listing.size_value} Sq.ft` : null,
  ].filter((value): value is string => Boolean(value));

  return (
    <article className="tenant-listing-card">
      <Link className="tenant-listing-link" href={listingHref(listing)} aria-label={`View ${listing.title}`}>
        <div className={`tenant-listing-photo${photo ? " has-photo" : ""}`}>
          <img src={photo ?? "/rentra-cards/d17d3.png"} alt="" loading="lazy" />
        </div>
        <div className="tenant-card-body">
          <div className="tenant-card-details">
            <span className="tenant-card-title">{listing.title}</span>
            {location ? <p className="tenant-card-location">{location}</p> : null}
            {specifications.length ? (
              <div className="tenant-card-specifications">
                {specifications.map((specification, index) => (
                  <span className="tenant-card-specification" key={specification}>
                    {index ? <img src="/rentra-cards/56c7d.svg" alt="" /> : null}
                    {specification}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
          <div className="tenant-card-footer">
            {rent ? <p className="tenant-card-price">{rent}</p> : null}
            <div className="tenant-card-status">
              <span className="tenant-card-active"><img src="/rentra-cards/26bc2.svg" alt="" />Active</span>
              {age ? <><img className="tenant-card-time-separator" src="/rentra-cards/5a07e.svg" alt="" /><time dateTime={listing.created_at}>{age}</time></> : null}
            </div>
          </div>
        </div>
      </Link>
      <button className="tenant-bookmark" type="button" aria-label={saved ? "Remove from saved listings" : "Save listing"} aria-pressed={saved} disabled={saving} onClick={onToggleSaved}>
        <img src={saved ? "/rentra-cards/83d3b.svg" : "/rentra-cards/47a19.svg"} alt="" />
      </button>
    </article>
  );
}
