import { redirect } from "next/navigation";
import { LoginForm } from "@/components/login-form";
import { getOptionalProfile } from "@/lib/server-auth";
import { hasSupabaseConfig } from "@/lib/supabase/env";

export const dynamic = "force-dynamic";

type LoginPageProps = {
  searchParams: Promise<{ error?: string; entry?: string }>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  let error = params.error;
  let nextPath: string | undefined;

  if (params.entry !== "home" && hasSupabaseConfig()) {
    try {
      const current = await getOptionalProfile();
      if (current) {
        nextPath = current.profile.active_role ? "/app" : "/onboarding/role";
      }
    } catch {
      error ??= "profile";
    }
  }

  if (nextPath) redirect(nextPath);
  return <LoginForm initialError={error} supabaseConfigured={hasSupabaseConfig()} />;
}
