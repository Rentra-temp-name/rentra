import { ListingDetail } from "@/components/listing-detail";

export default async function ListingPage({ params }: { params: Promise<{ "listing-slug": string }> }) {
  const { "listing-slug": slug } = await params;
  return <ListingDetail slug={slug} />;
}
