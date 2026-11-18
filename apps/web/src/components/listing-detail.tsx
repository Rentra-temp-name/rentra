"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { FigmaListingDetail } from "@/components/figma-listing-detail";
import "./listing-detail-handoff.css";

type Photo = { id: string; position: number; width: number; height: number; original_url: string; thumb_url: string | null };
export type ListingDetailData = {
  id: string;
  title: string;
  location_label?: string;
  rent_amount: string;
  display_name: string | null;
  point?: { latitude: number; longitude: number };
  whatsapp: string | null;
  created_at: string;
  photos: Photo[];
  numeric: Record<string, string>;
  answers: Record<string, string[]>;
};

const apiBase = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");

function previewListing(slug: string): ListingDetailData | null {
  const featured = slug.endsWith("-featured-preview");
  const cardPreview = /-(for-you|new-listings|saved)-preview-\d+$/.test(slug);
  if (!featured && !cardPreview) return null;
  return {
    id: featured ? "featured-preview" : slug.match(/((?:for-you|new-listings|saved)-preview-\d+)$/)?.[1] ?? "card-preview",
    title: featured ? "Narayanchaur, Naxal" : "Semi-Furnished Apartment",
    location_label: featured ? "Narayanchaur, Naxal" : "Budhanilkantha, Kathmandu",
    rent_amount: featured ? "100000" : "70000",
    display_name: "Rentra Preview",
    whatsapp: null,
    created_at: new Date(Date.now() - 2 * 86_400_000).toISOString(),
    photos: [{ id: "preview-photo", position: 1, width: 624, height: 418, original_url: "/assets/11b5b.png", thumb_url: null }],
    numeric: featured ? { bedrooms: "2", bathrooms_total: "3" } : { bedrooms: "1", bathrooms_total: "1", size_value: "5000" },
    answers: {},
  };
}

export function ListingDetail({ slug }: { slug: string }) {
  const [listing, setListing] = useState<ListingDetailData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError("");
      setListing(null);
      const preview = previewListing(slug);
      if (preview) {
        setListing(preview);
        setLoading(false);
        return;
      }
      try {
        if (!apiBase) throw new Error("Listing details are temporarily unavailable.");
        const response = await fetch(`${apiBase}/listings/${encodeURIComponent(slug)}`, { cache: "no-store" });
        if (!response.ok) throw new Error(response.status === 404 ? "This listing is no longer available." : "Could not load this listing. Please try again.");
        const result = await response.json() as ListingDetailData;
        if (active) setListing({ ...result, photos: result.photos ?? [], numeric: result.numeric ?? {}, answers: result.answers ?? {} });
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : "Could not load this listing.");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, [slug]);

  if (loading) return <section className="listing-handoff-state" aria-live="polite">Loading listing details</section>;
  if (error || !listing) return <section className="listing-handoff-state listing-handoff-state--error"><Link href="/app"><ArrowLeft size={18} /> Back to listings</Link><h1>Listing unavailable</h1><p>{error || "This listing could not be found."}</p></section>;
  return <FigmaListingDetail listing={listing} />;
}
