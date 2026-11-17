import { NextRequest, NextResponse } from "next/server";
import { displayNameFromMetadata, getMyProfile, updateMyProfile } from "@/lib/api";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export async function GET(request: NextRequest) {
  const requestUrl = new URL(request.url);
  const code = requestUrl.searchParams.get("code");
  if (!code) {
    return NextResponse.redirect(new URL("/login?error=callback", requestUrl.origin));
  }

  try {
    const supabase = await createSupabaseServerClient();
    const { data, error } = await supabase.auth.exchangeCodeForSession(code);
    if (error || !data.session?.access_token) {
      return NextResponse.redirect(new URL("/login?error=oauth", requestUrl.origin));
    }

    const profile = await getMyProfile(data.session.access_token);
    const displayName = displayNameFromMetadata(data.user?.user_metadata, data.user?.email);
    if (!profile.display_name && displayName) {
      await updateMyProfile(data.session.access_token, { display_name: displayName });
    }
    const destination = profile.active_role ? "/app" : "/onboarding/role";
    return NextResponse.redirect(new URL(destination, requestUrl.origin));
  } catch {
    return NextResponse.redirect(new URL("/login?error=profile", requestUrl.origin));
  }
}
