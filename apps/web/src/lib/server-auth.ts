import { redirect } from "next/navigation";
import { getMyProfile, type Profile } from "@/lib/api";
import { hasSupabaseConfig } from "@/lib/supabase/env";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export async function getOptionalProfile(): Promise<{ profile: Profile; accessToken: string } | null> {
  if (!hasSupabaseConfig()) return null;

  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.auth.getClaims();
  if (error || !data?.claims) return null;

  const { data: { session } } = await supabase.auth.getSession();
  if (!session?.access_token) return null;

  const profile = await getMyProfile(session.access_token);
  return { profile, accessToken: session.access_token };
}

export async function requireProfile(): Promise<{ profile: Profile; accessToken: string }> {
  if (!hasSupabaseConfig()) redirect("/login?error=missing_config");

  const result = await getOptionalProfile();
  if (!result) redirect("/login");
  return result;
}
