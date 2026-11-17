import { AppShell } from "@/components/app-shell";
import { TenantHome } from "@/components/tenant-home";
import { requireProfile } from "@/lib/server-auth";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function AppHomePage() {
  const { profile } = await requireProfile();
  if (!profile.active_role) redirect("/onboarding/role");

  return (
    <AppShell activeRole={profile.active_role}>
      {profile.active_role === "tenant" ? (
        <TenantHome displayName={profile.display_name} />
      ) : (
        <section className="home-placeholder" aria-label="Landlord home">
          <h1>Your listings</h1>
        </section>
      )}
    </AppShell>
  );
}
