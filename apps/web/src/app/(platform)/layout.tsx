import { AppShell } from "@/components/app-shell";
import { hasSupabaseConfig } from "@/lib/supabase/env";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export default async function PlatformLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  let signedIn = false;
  if (hasSupabaseConfig()) {
    try {
      const supabase = await createSupabaseServerClient();
      const { data } = await supabase.auth.getSession();
      signedIn = Boolean(data.session);
    } catch {
      signedIn = false;
    }
  }

  return <AppShell signedIn={signedIn}>{children}</AppShell>;
}
