"use client";

import { Check, House, MapPinSearch } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { BrandPanel } from "@/components/brand-panel";
import type { ActiveRole } from "@/lib/api";
import { displayNameFromMetadata, updateActiveRole } from "@/lib/api";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";

export function RolePicker() {
  const router = useRouter();
  const [selectedRole, setSelectedRole] = useState<ActiveRole | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function getStarted() {
    if (!selectedRole || saving) return;
    setSaving(true);
    setError("");

    try {
      const supabase = createSupabaseBrowserClient();
      const { data: { session }, error: sessionError } = await supabase.auth.getSession();
      if (sessionError || !session?.access_token) throw new Error("Your session expired. Sign in again.");
      const displayName = displayNameFromMetadata(session.user.user_metadata, session.user.email);
      await updateActiveRole(session.access_token, selectedRole, displayName);
      router.replace("/app");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save your choice. Try again.");
      setSaving(false);
    }
  }

  return (
    <div className="split-auth-layout">
      <BrandPanel />
      <main className="split-auth-main">
        <section className="auth-flow role-flow" aria-labelledby="role-title">
          <div className="auth-progress" aria-hidden="true"><i className="is-done" /><i className="is-done" /></div>
          <h1 id="role-title">What brings you to Rentra?</h1>
          <p className="auth-subtitle">Pick one. You can change this later in settings.</p>

          <div className="role-options" role="radiogroup" aria-labelledby="role-title">
            <label className={`role-option${selectedRole === "tenant" ? " is-selected" : ""}`}>
              <input
                type="radio"
                name="active-role"
                value="tenant"
                checked={selectedRole === "tenant"}
                onChange={() => setSelectedRole("tenant")}
              />
              <span className="role-icon"><MapPinSearch aria-hidden="true" /></span>
              <span className="role-copy">
                <span className="role-name">Tenant</span>
                <span className="role-description">I'm looking for a place to rent</span>
              </span>
              <span className="role-tick"><Check aria-hidden="true" /></span>
            </label>
            <label className={`role-option${selectedRole === "landlord" ? " is-selected" : ""}`}>
              <input
                type="radio"
                name="active-role"
                value="landlord"
                checked={selectedRole === "landlord"}
                onChange={() => setSelectedRole("landlord")}
              />
              <span className="role-icon"><House aria-hidden="true" /></span>
              <span className="role-copy">
                <span className="role-name">Landlord</span>
                <span className="role-description">I want to list my properties</span>
              </span>
              <span className="role-tick"><Check aria-hidden="true" /></span>
            </label>
          </div>

          <button
            className="flow-button primary-flow-button"
            type="button"
            disabled={!selectedRole || saving}
            onClick={getStarted}
          >
            {saving ? "Saving…" : "Continue"}
          </button>
          {error ? <p className="flow-error" role="alert">{error}</p> : null}
        </section>
      </main>
    </div>
  );
}
