import { RolePicker } from "@/components/role-picker";
import { requireProfile } from "@/lib/server-auth";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function RoleOnboardingPage() {
  const { profile } = await requireProfile();
  if (profile.active_role) redirect("/app");

  return <RolePicker />;
}
