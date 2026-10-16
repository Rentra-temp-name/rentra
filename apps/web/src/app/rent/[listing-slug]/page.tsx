export default async function ListingPage({ params }: { params: Promise<{ "listing-slug": string }> }) {
  const { "listing-slug": slug } = await params;
  return <main className="simple-page"><p className="eyebrow">Rental listing</p><h1>Listing details</h1><p>Listing “{slug}” is not available until the listings API is connected.</p></main>;
}
