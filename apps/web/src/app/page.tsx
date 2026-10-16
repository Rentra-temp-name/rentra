import Link from "next/link";

export default function HomePage() {
  return (
    <main>
      <header className="site-header">
        <Link className="brand" href="/">Rentra</Link>
        <nav aria-label="Main navigation">
          <Link href="/rent">Rent</Link>
          <Link href="/list">List a property</Link>
          <Link href="/about">About</Link>
          <Link href="/contact">Contact</Link>
          <Link href="/account">Log in</Link>
        </nav>
      </header>
      <section className="hero">
        <p className="eyebrow">A place to call home</p>
        <h1>Find your next place in Nepal.</h1>
        <p className="intro">Explore apartments, hostels, and commercial spaces from local landlords.</p>
        <form action="/rent" className="search" role="search">
          <label className="sr-only" htmlFor="area">Area or city</label>
          <input id="area" name="q" placeholder="Where do you want to live?" />
          <button type="submit">Search rentals</button>
        </form>
      </section>
      <section className="map-panel" aria-labelledby="map-title">
        <div>
          <p className="eyebrow">Find your area</p>
          <h2 id="map-title">Explore rentals on the map</h2>
          <p>The live map will be added after the map provider is selected.</p>
        </div>
        <Link className="secondary-button" href="/map">View map</Link>
      </section>
      <section className="listings" aria-labelledby="listings-title">
        <div><p className="eyebrow">A fresh start</p><h2 id="listings-title">Places to explore</h2></div>
        <p>New rental listings will appear here.</p>
        <Link className="text-link" href="/rent">View all rentals →</Link>
      </section>
      <section className="landlord-cta">
        <h2>Have a place to rent?</h2>
        <p>Reach people looking for their next home.</p>
        <Link className="secondary-button" href="/list">List a property</Link>
      </section>
      <footer><span>Rentra</span><span>Helping Nepal find a place to call home.</span></footer>
    </main>
  );
}
