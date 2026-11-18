"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, RefreshCw } from "lucide-react";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import { MainCard, type MainCardListing } from "@/components/main-card";
import { FeaturedCard } from "@/components/featured-card";

type Listing = MainCardListing;

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

async function getCardDetails(listing: Listing, token: string): Promise<Listing> {
  try {
    const details = await getJson<Listing>(`/listings/${listing.id}`, token);
    return {
      ...listing,
      ...details,
      bedrooms: details.numeric?.bedrooms ?? details.bedrooms ?? listing.bedrooms,
      bathrooms_total: details.numeric?.bathrooms_total ?? details.bathrooms_total ?? listing.bathrooms_total,
      size_value: details.numeric?.size_value ?? details.size_value ?? listing.size_value,
    };
  } catch {
    return listing;
  }
}

function uniqueListings(listings: Listing[]) {
  return [...new Map(listings.map((listing) => [listing.id, listing])).values()];
}

function previewListings(prefix: string): Listing[] {
  const createdAt = new Date(Date.now() - 2 * 86_400_000).toISOString();
  return [1, 2, 3].map((number) => ({
    id: `${prefix}-preview-${number}`,
    title: "Semi-Furnished Apartment",
    location_label: "Budhanilkantha, Kathmandu",
    bedrooms: 1,
    bathrooms_total: 1,
    size_value: 5000,
    rent_amount: "70000",
    created_at: createdAt,
    photos: [{ original_url: "/rentra-cards/d17d3.png", thumb_url: "/rentra-cards/d17d3.png" }],
    is_preview: true,
  }));
}

const featuredPreview: Listing = {
  id: "featured-preview",
  title: "Narayanchaur, Naxal",
  bedrooms: 2,
  bathrooms_total: 3,
  rent_amount: "100000",
  photos: [{ original_url: "/rentra-cards/16862.png" }],
  is_preview: true,
};

export function TenantHome({ firstName }: { firstName: string }) {
  const [forYou, setForYou] = useState<Listing[]>([]);
  const [newListings, setNewListings] = useState<Listing[]>([]);
  const [savedListings, setSavedListings] = useState<Listing[]>([]);
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set());
  const [previewSavedIds, setPreviewSavedIds] = useState<Set<string>>(new Set(["saved-preview-1"]));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [savingIds, setSavingIds] = useState<Set<string>>(new Set());
  const [bookmarkError, setBookmarkError] = useState("");
  const [greeting, setGreeting] = useState("Good morning");

  useEffect(() => {
    const hour = new Date().getHours();
    setGreeting(hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening");
  }, []);

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
          const matchedListings = uniqueListings([
            ...(matches.perfect ?? []),
            ...(matches.ranked ?? []).map((item) => item.listing),
            ...(matches.explore_listings ?? []),
          ]).slice(0, 6);
          setForYou(matchedListings);
          const details = await Promise.all(matchedListings.map((listing) => getCardDetails(listing, session.access_token)));
          if (active) setForYou(details);
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
          const details = await Promise.all((feedResult.value.listings ?? []).map((listing) => getCardDetails(listing, session.access_token)));
          if (active) setNewListings(details);
        }
        if (savedResult.status === "fulfilled") {
          const visibleSaved = (savedResult.value.saved ?? []).filter((item) => item.visible !== false);
          const details = await Promise.all(visibleSaved.map((listing) => getCardDetails(listing, session.access_token)));
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
    if (listing.is_preview) {
      setPreviewSavedIds((current) => {
        const next = new Set(current);
        if (next.has(listing.id)) next.delete(listing.id);
        else next.add(listing.id);
        return next;
      });
      return;
    }
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
        <h1>{greeting}, {firstName}</h1>
        <p>Matched rentals, new listings, and places you’ve saved.</p>
      </header>

      {bookmarkError ? <p className="tenant-inline-error" role="alert">{bookmarkError}</p> : null}
      {error ? (
        <div className="tenant-load-error" role="alert">
          <p>{error}</p>
          <button className="tenant-retry" type="button" onClick={() => window.location.reload()}><RefreshCw aria-hidden="true" /> Try again</button>
        </div>
      ) : null}

      <div className="tenant-sections" aria-busy={loading}>
        <ListingSection title="For You" listings={forYou} loading={loading} savedIds={savedIds} previewSavedIds={previewSavedIds} savingIds={savingIds} onToggleSaved={toggleSaved} />
        <FeaturedSection
          loading={loading}
          listings={(() => {
            const allListings = uniqueListings([...forYou, ...newListings]);
            const featuredListings = allListings.filter((listing) => listing.is_featured);
            return featuredListings.length ? featuredListings : allListings;
          })()}
        />
        <ListingSection title="New Listings" listings={newListings} loading={loading} savedIds={savedIds} previewSavedIds={previewSavedIds} savingIds={savingIds} onToggleSaved={toggleSaved} />
        <ListingSection title="Your Saved Listings" listings={savedListings} loading={loading} savedIds={savedIds} previewSavedIds={previewSavedIds} savingIds={savingIds} onToggleSaved={toggleSaved} />
      </div>
    </div>
  );
}

function ListingSection({
  title,
  listings,
  loading,
  savedIds,
  previewSavedIds,
  savingIds,
  onToggleSaved,
}: {
  title: string;
  listings: Listing[];
  loading: boolean;
  savedIds: Set<string>;
  previewSavedIds: Set<string>;
  savingIds: Set<string>;
  onToggleSaved: (listing: Listing) => void;
}) {
  const previewPrefix = title === "Your Saved Listings" ? "saved" : title.replace(/\W+/g, "-").toLowerCase();
  const displayedListings = listings.length ? listings : previewListings(previewPrefix);
  return (
    <section className="tenant-listing-section" aria-label={title}>
      <div className="tenant-section-heading">
        <h2>{title}</h2>
      </div>
      {loading ? (
        <div className="tenant-listing-grid" aria-hidden="true">
          {[0, 1, 2].map((item) => <ListingSkeleton key={item} />)}
        </div>
      ) : displayedListings.length ? (
        <div className="tenant-listing-grid">
          {displayedListings.map((listing) => (
            <MainCard key={listing.id} listing={listing} saved={listing.is_preview ? previewSavedIds.has(listing.id) : savedIds.has(listing.id)} saving={savingIds.has(listing.id)} onToggleSaved={() => onToggleSaved(listing)} />
          ))}
        </div>
      ) : (
        <p className="tenant-empty-state">
          {title === "Your Saved Listings" ? "Save a home you like and it will show up here." : title === "For You" ? "Homes that match your search will appear here." : "New rental listings will appear here when they’re available."}
        </p>
      )}
      <Link className="tenant-section-link" href={title === "Your Saved Listings" ? "/saved" : "/rent"}>
        Browse all <ArrowRight aria-hidden="true" />
      </Link>
    </section>
  );
}

function ListingSkeleton() {
  return (
    <div className="tenant-listing-skeleton">
      <div className="tenant-skeleton-photo" />
      <div className="tenant-skeleton-body" aria-hidden="true">
        <div className="tenant-skeleton-details"><i /><i /><i /></div>
        <div className="tenant-skeleton-footer">
          <i className="tenant-skeleton-price" />
          <div className="tenant-skeleton-status"><i /><i /><i /></div>
        </div>
      </div>
    </div>
  );
}

function FeaturedSection({ loading, listings }: { loading: boolean; listings: Listing[] }) {
  const [slide, setSlide] = useState(0);
  const preview = listings.length === 0;
  const visibleListings = preview ? [featuredPreview] : uniqueListings(listings).slice(0, 3);
  const featured = visibleListings[slide] ?? featuredPreview;
  return (
    <section className="tenant-featured-section" aria-label="Featured">
      <h2>Featured</h2>
      {loading ? <div className="tenant-featured-skeleton" aria-hidden="true" /> : (
        featured ? <FeaturedCard listing={featured} /> : <div className="tenant-featured-empty"><p>Featured homes will appear here as they become available.</p></div>
      )}
      {preview ? <img className="tenant-featured-reference-dots" src="/rentra-cards/60d02.svg" alt="Featured slide 2 of 3" /> : visibleListings.length > 1 ? (
        <div className="tenant-featured-dots" aria-label="Featured property carousel">
          {visibleListings.map((listing, index) => <button key={listing.id} className={index === slide ? "is-active" : ""} type="button" aria-label={`Show featured property ${index + 1}`} aria-pressed={index === slide} onClick={() => setSlide(index)} />)}
        </div>
      ) : null}
      <Link className="tenant-section-link tenant-featured-browse-all" href="/rent">
        Browse all <ArrowRight aria-hidden="true" />
      </Link>
    </section>
  );
}
