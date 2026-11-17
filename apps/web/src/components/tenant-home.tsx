"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Bookmark, MapPin, RefreshCw } from "lucide-react";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";

type Point = { latitude: number; longitude: number };
type ListingPhoto = { original_url?: string; thumb_url?: string };
type Listing = {
  id: string;
  title: string;
  rent_amount?: string;
  rent?: string;
  point?: Point;
  photos?: ListingPhoto[];
  created_at?: string;
  visible?: boolean;
  is_featured?: boolean;
};

type FeedResponse = { listings?: Listing[]; next_cursor?: string | null };
type MatchesResponse = {
  perfect?: Listing[];
  ranked?: { listing: Listing }[];
  explore_listings?: Listing[];
};
type SavedResponse = { saved?: Listing[] };

const apiBase = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");

async function getJson<T>(path: string, token: string): Promise<T> {
  if (!apiBase) throw new Error("Rental search is not connected yet.");
  const response = await fetch(`${apiBase}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(response.status === 503 ? "Listings are temporarily unavailable." : "Could not load listings. Please try again.");
  return (await response.json()) as T;
}

function uniqueListings(listings: Listing[]) {
  return [...new Map(listings.map((listing) => [listing.id, listing])).values()];
}

function listingHref(listing: Listing) {
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

export function TenantHome({ displayName }: { displayName: string | null }) {
  const [forYou, setForYou] = useState<Listing[]>([]);
  const [newListings, setNewListings] = useState<Listing[]>([]);
  const [savedListings, setSavedListings] = useState<Listing[]>([]);
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [savingIds, setSavingIds] = useState<Set<string>>(new Set());
  const [bookmarkError, setBookmarkError] = useState("");

  const [greeting, setGreeting] = useState("Good afternoon");

  useEffect(() => {
    const hour = new Date().getHours();
    const timeOfDay = hour < 12 ? "Morning" : hour < 17 ? "Afternoon" : "Evening";
    const name = displayName?.trim().split(/\s+/)[0];
    setGreeting(`Good ${timeOfDay}${name ? `, ${name}` : ""}`);
  }, [displayName]);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const supabase = createSupabaseBrowserClient();
        const { data: { session }, error: sessionError } = await supabase.auth.getSession();
        if (sessionError || !session?.access_token) throw new Error("Your session expired. Sign in again.");
        const [matchesResult, feedResult, savedResult] = await Promise.allSettled([
          getJson<MatchesResponse>("/matches?page_size=6", session.access_token),
          getJson<FeedResponse>("/listings?page_size=6", session.access_token),
          getJson<SavedResponse>("/me/saved?page_size=6", session.access_token),
        ]);
        if (!active) return;
        if (matchesResult.status === "fulfilled") {
          const matches = matchesResult.value;
          setForYou(uniqueListings([
            ...(matches.perfect ?? []),
            ...(matches.ranked ?? []).map((item) => item.listing),
            ...(matches.explore_listings ?? []),
          ]).slice(0, 6));
        }
        if (feedResult.status === "fulfilled") setNewListings(feedResult.value.listings ?? []);
        if (savedResult.status === "fulfilled") {
          const saved = (savedResult.value.saved ?? []).filter((item) => item.visible !== false);
          setSavedListings(saved);
          setSavedIds(new Set((savedResult.value.saved ?? []).map((item) => item.id)));
        }
        const failures = [matchesResult, feedResult, savedResult].filter((result) => result.status === "rejected");
        if (failures.length === 3) throw new Error((failures[0] as PromiseRejectedResult).reason instanceof Error ? (failures[0] as PromiseRejectedResult).reason.message : "Listings are unavailable right now.");
        // The public feed does not include photos; hydrate only its visible cards from the public detail endpoint.
        if (feedResult.status === "fulfilled") {
          const details = await Promise.all((feedResult.value.listings ?? []).map(async (listing) => {
            try {
              return await getJson<Listing>(`/listings/${listing.id}`, session.access_token);
            } catch {
              return listing;
            }
          }));
          if (active) setNewListings(details);
        }
        if (savedResult.status === "fulfilled") {
          const visibleSaved = (savedResult.value.saved ?? []).filter((item) => item.visible !== false);
          const details = await Promise.all(visibleSaved.map(async (listing) => {
            try {
              return { ...listing, ...await getJson<Listing>(`/listings/${listing.id}`, session.access_token) };
            } catch {
              return listing;
            }
          }));
          if (active) setSavedListings(details);
        }
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : "Could not load your home. Please try again.");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, []);

  async function toggleSaved(listing: Listing) {
    if (savingIds.has(listing.id)) return;
    const wasSaved = savedIds.has(listing.id);
    setSavingIds((current) => new Set(current).add(listing.id));
    setBookmarkError("");
    try {
      const supabase = createSupabaseBrowserClient();
      const { data: { session }, error: sessionError } = await supabase.auth.getSession();
      if (sessionError || !session?.access_token || !apiBase) throw new Error("Could not update saved listings. Please try again.");
      const response = await fetch(`${apiBase}/listings/${listing.id}/save`, {
        method: wasSaved ? "DELETE" : "POST",
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (!response.ok) throw new Error("Could not update saved listings. Please try again.");
      setSavedIds((current) => {
        const next = new Set(current);
        if (wasSaved) next.delete(listing.id);
        else next.add(listing.id);
        return next;
      });
      if (wasSaved) setSavedListings((current) => current.filter((item) => item.id !== listing.id));
      else setSavedListings((current) => [listing, ...current].slice(0, 6));
    } catch (caught) {
      setBookmarkError(caught instanceof Error ? caught.message : "Could not update saved listings.");
    } finally {
      setSavingIds((current) => {
        const next = new Set(current);
        next.delete(listing.id);
        return next;
      });
    }
  }

  return (
    <div className="tenant-home" aria-label="Tenant home">
      <header className="tenant-welcome">
        <h1>{greeting}</h1>
        <p>Let’s see if there are any updates on your property hunt.</p>
      </header>

      {bookmarkError ? <p className="tenant-inline-error" role="alert">{bookmarkError}</p> : null}
      {error ? (
        <div className="tenant-load-error" role="alert">
          <p>{error}</p>
          <button className="tenant-retry" type="button" onClick={() => window.location.reload()}><RefreshCw aria-hidden="true" /> Try again</button>
        </div>
      ) : null}

      <div className="tenant-sections" aria-busy={loading}>
        <ListingSection title="For You" listings={forYou} loading={loading} savedIds={savedIds} savingIds={savingIds} onToggleSaved={toggleSaved} />
        <FeaturedSection loading={loading} listings={[...forYou, ...newListings].filter((listing) => listing.is_featured)} />
        <ListingSection title="New Listings" listings={newListings} loading={loading} savedIds={savedIds} savingIds={savingIds} onToggleSaved={toggleSaved} />
        <ListingSection title="Your Saved Listings" listings={savedListings} loading={loading} savedIds={savedIds} savingIds={savingIds} onToggleSaved={toggleSaved} />
      </div>
    </div>
  );
}

function ListingSection({
  title,
  listings,
  loading,
  savedIds,
  savingIds,
  onToggleSaved,
}: {
  title: string;
  listings: Listing[];
  loading: boolean;
  savedIds: Set<string>;
  savingIds: Set<string>;
  onToggleSaved: (listing: Listing) => void;
}) {
  return (
    <section className="tenant-listing-section" aria-label={title}>
      <div className="tenant-section-heading">
        <h2>{title}</h2>
      </div>
      {loading ? (
        <div className="tenant-listing-grid" aria-hidden="true">
          {[0, 1, 2].map((item) => <ListingSkeleton key={item} />)}
        </div>
      ) : listings.length ? (
        <div className="tenant-listing-grid">
          {listings.map((listing) => (
            <ListingCard key={listing.id} listing={listing} saved={savedIds.has(listing.id)} saving={savingIds.has(listing.id)} onToggleSaved={() => onToggleSaved(listing)} />
          ))}
        </div>
      ) : (
        <p className="tenant-empty-state">
          {title === "Your Saved Listings" ? "Save a home you like and it will show up here." : title === "For You" ? "Homes that match your search will appear here." : "New rental listings will appear here when they’re available."}
        </p>
      )}
    </section>
  );
}

function ListingCard({ listing, saved, saving, onToggleSaved }: { listing: Listing; saved: boolean; saving: boolean; onToggleSaved: () => void }) {
  const photo = listing.photos?.[0]?.thumb_url ?? listing.photos?.[0]?.original_url;
  const location = listingLocation(listing.point);
  const rent = formatRent(listing.rent_amount ?? listing.rent);
  const age = postedAge(listing.created_at);
  return (
    <article className="tenant-listing-card">
      <Link className={`tenant-listing-photo${photo ? " has-photo" : ""}`} href={listingHref(listing)} aria-label={`View ${listing.title}`}>
        {photo ? <img src={photo} alt="" loading="lazy" /> : <span className="tenant-photo-fallback"><MapPin aria-hidden="true" /> Property photo unavailable</span>}
      </Link>
      <button className="tenant-bookmark" type="button" aria-label={saved ? "Remove from saved listings" : "Save listing"} aria-pressed={saved} disabled={saving} onClick={onToggleSaved}>
        <Bookmark aria-hidden="true" fill={saved ? "currentColor" : "none"} />
      </button>
      <div className="tenant-card-body">
        <div className="tenant-card-details">
          <Link className="tenant-card-title" href={listingHref(listing)}>{listing.title}</Link>
          {location ? <p className="tenant-card-location"><MapPin aria-hidden="true" />{location}</p> : null}
        </div>
        <div className="tenant-card-footer">
          {rent ? <p className="tenant-card-price">{rent}</p> : null}
          <div className="tenant-card-status"><span><i aria-hidden="true" />Available</span>{age ? <time dateTime={listing.created_at}>{age}</time> : null}</div>
        </div>
      </div>
    </article>
  );
}

function ListingSkeleton() {
  return <div className="tenant-listing-skeleton"><div className="tenant-skeleton-photo" /><div className="tenant-skeleton-copy"><i /><i /><i /></div></div>;
}

function FeaturedSection({ loading, listings }: { loading: boolean; listings: Listing[] }) {
  const [slide, setSlide] = useState(0);
  const visibleListings = uniqueListings(listings).slice(0, 3);
  const featured = visibleListings[slide];
  return (
    <section className="tenant-featured-section" aria-label="Featured">
      <h2>Featured</h2>
      {loading ? <div className="tenant-featured-skeleton" aria-hidden="true" /> : (
        featured ? (
          <Link className="tenant-featured-property" href={listingHref(featured)} aria-label={`View featured property ${featured.title}`}>
            {featured.photos?.[0]?.original_url ? <img className="tenant-featured-image" src={featured.photos[0].original_url} alt="" /> : <span className="tenant-featured-no-photo"><MapPin aria-hidden="true" /> Property photo unavailable</span>}
            <span className="tenant-featured-shade" />
            <span className="tenant-featured-details">
              <strong>{featured.title}</strong>
              {listingLocation(featured.point) ? <span className="tenant-featured-location"><MapPin aria-hidden="true" />{listingLocation(featured.point)}</span> : null}
              {formatRent(featured.rent_amount ?? featured.rent) ? <span>{formatRent(featured.rent_amount ?? featured.rent)}</span> : null}
            </span>
          </Link>
        ) : <div className="tenant-featured-empty"><p>Featured homes will appear here as they become available.</p></div>
      )}
      {visibleListings.length > 1 ? (
        <div className="tenant-featured-dots" aria-label="Featured property carousel">
          {visibleListings.map((listing, index) => <button key={listing.id} className={index === slide ? "is-active" : ""} type="button" aria-label={`Show featured property ${index + 1}`} aria-pressed={index === slide} onClick={() => setSlide(index)} />)}
        </div>
      ) : null}
      <Link className="tenant-button" href="/rent"><span>Browse all <ArrowRight aria-hidden="true" /></span></Link>
    </section>
  );
}
