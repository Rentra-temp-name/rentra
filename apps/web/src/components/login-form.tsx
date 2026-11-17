"use client";

import Image from "next/image";
import { useState, type FormEvent } from "react";
import { BrandPanel } from "@/components/brand-panel";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";

type LoginFormProps = {
  initialError?: string;
  supabaseConfigured: boolean;
};

const messages: Record<string, string> = {
  missing_config: "Add your Supabase anon key to apps/web/.env to enable sign-in.",
  oauth: "Google sign-in could not be completed. Please try again.",
  callback: "Sign-in could not be completed. Please try again.",
  profile: "Your profile could not be loaded. Check that the API is running and try again.",
};

export function LoginForm({ initialError, supabaseConfigured }: LoginFormProps) {
  const [error, setError] = useState(initialError ? messages[initialError] ?? messages.oauth : "");
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState("");

  async function signInWithGoogle() {
    setError("");
    if (!supabaseConfigured) {
      setError("Add NEXT_PUBLIC_SUPABASE_ANON_KEY to apps/web/.env, then restart the web app.");
      return;
    }

    setBusy(true);
    try {
      const supabase = createSupabaseBrowserClient();
      const { error: signInError } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
        },
      });
      if (signInError) throw signInError;
    } catch {
      setBusy(false);
      setError("Google sign-in could not be started. Check the Supabase settings and try again.");
    }
  }

  function handleEmailSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedEmail = email.trim();
    const isValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail);
    setEmailError(isValid ? "" : "Enter a valid email address, like name@example.com.");
    if (isValid) console.log("email signup", { email: normalizedEmail });
  }

  return (
    <div className="split-auth-layout">
      <BrandPanel />
      <main className="split-auth-main">
        <section className="auth-flow login-flow" aria-labelledby="login-title">
          <div className="auth-progress" aria-hidden="true"><i className="is-done" /><i /></div>
          <h1 id="login-title">Create your account</h1>
          <p className="auth-subtitle">Looking for rentals in Nepal has never been easier.</p>

          <div className="login-controls">
            <button
              className="flow-button outline-button"
              id="google"
              type="button"
              onClick={signInWithGoogle}
              disabled={busy}
            >
              <Image
                src="/GoogleG_FullColor_RGB.png"
                alt=""
                aria-hidden="true"
                suppressHydrationWarning
                width={20}
                height={20}
                className="google-mark"
              />
              {busy ? "Connecting…" : "Continue with Google"}
            </button>

            <div className="email-divider">or use your email</div>

            <form className="email-form" onSubmit={handleEmailSubmit} noValidate>
              <div className="email-field">
                <label htmlFor="email">Email</label>
                <input
                  className="auth-input"
                  id="email"
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  aria-invalid={emailError ? "true" : "false"}
                  aria-describedby="email-error"
                  value={email}
                  onChange={(event) => {
                    setEmail(event.target.value);
                    setEmailError("");
                  }}
                />
                <p className="field-error" id="email-error" role="alert">{emailError}</p>
              </div>
              <button className="flow-button primary-flow-button" type="submit">Sign up</button>
            </form>

            <p className="account-hint">
              Already have an account? <button type="button" onClick={signInWithGoogle}>Log in</button>
            </p>
            {error ? <p className="flow-error" role="alert">{error}</p> : null}
            {!supabaseConfigured && !error ? (
              <p className="flow-error" role="note">Add NEXT_PUBLIC_SUPABASE_ANON_KEY to apps/web/.env to enable Google sign-in.</p>
            ) : null}
          </div>
        </section>
      </main>
    </div>
  );
}
