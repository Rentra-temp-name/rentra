import { TenantHome } from "@/components/tenant-home";
import { requireProfile } from "@/lib/server-auth";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function AppHomePage() {
  const { profile } = await requireProfile();
  if (!profile.active_role) redirect("/onboarding/role");

  return profile.active_role === "tenant" ? (
    <TenantHome firstName={profile.display_name?.trim().split(/\s+/)[0] || "there"} />
  ) : (
    <section className="home-placeholder" aria-label="Landlord home">
      <h1>Your listings</h1>
    </section>
  );
}
