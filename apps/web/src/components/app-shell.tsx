"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { Bell, Bookmark, House, LogOut, MapPinSearch, UserRound, type LucideIcon } from "lucide-react";
import type { ActiveRole } from "@/lib/api";
import { updateActiveRole } from "@/lib/api";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import "./app-shell-overrides.css";

type AppShellProps = {
  activeRole: ActiveRole;
  children: React.ReactNode;
};

type NavItem = {
  label: string;
  href: string;
  Icon: LucideIcon;
  matchPrefix?: boolean;
};

const navItems: NavItem[] = [
  { label: "Home", href: "/app", Icon: House, matchPrefix: true },
  { label: "Map search", href: "/map", Icon: MapPinSearch, matchPrefix: true },
  { label: "Saved listings", href: "/saved", Icon: Bookmark, matchPrefix: true },
];

export function AppShell({ activeRole, children }: AppShellProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [expanded, setExpanded] = useState(false);
  const [savingRole, setSavingRole] = useState(false);
  const [error, setError] = useState("");

  function isActive(item: NavItem) {
    if (!pathname) return false;
    if (pathname === item.href) return true;
    return Boolean(item.matchPrefix && pathname.startsWith(`${item.href}/`));
  }

  async function switchRole(nextRole: ActiveRole) {
    if (nextRole === activeRole || savingRole) return;
    setSavingRole(true);
    setError("");

    try {
      const supabase = createSupabaseBrowserClient();
      const { data: { session }, error: sessionError } = await supabase.auth.getSession();
      if (sessionError || !session?.access_token) throw new Error("Your session expired. Sign in again.");
      await updateActiveRole(session.access_token, nextRole);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not switch mode. Try again.");
    } finally {
      setSavingRole(false);
    }
  }

  async function signOut() {
    setError("");
    const supabase = createSupabaseBrowserClient();
    const { error: signOutError } = await supabase.auth.signOut({ scope: "local" });
    if (signOutError) {
      setError("Could not sign out. Please try again.");
      return;
    }
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="app-shell">
      <aside className="app-sidebar" data-expanded={expanded} aria-label="Main navigation">
        <button
          className="sidebar-logo sidebar-logo--text"
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-label={expanded ? "Collapse sidebar" : "Expand sidebar"}
          aria-expanded={expanded}
          title={expanded ? "Collapse sidebar" : "Expand sidebar"}
        >
          <span aria-hidden="true">{expanded ? "rentra" : "r"}</span>
        </button>
        <nav className="sidebar-nav">
          {navItems.map(({ label, href, Icon, ...item }) => {
            const active = isActive({ label, href, Icon, ...item });
            return (
              <Link
                key={href}
                className={`sidebar-link${active ? " is-active" : ""}`}
                href={href}
                aria-label={label}
                aria-current={active ? "page" : undefined}
                title={!expanded ? label : undefined}
              >
                {active && Icon === House ? (
                  <svg className="sidebar-icon sidebar-icon--house" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path
                      d="M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8"
                      fillRule="evenodd"
                      clipRule="evenodd"
                      stroke="currentColor"
                      strokeWidth="1.7"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : (
                  <Icon
                    className={`sidebar-icon sidebar-icon--${href.slice(1)}`}
                    aria-hidden="true"
                    strokeWidth={1.7}
                  />
                )}
                <span className="sidebar-link-label" aria-hidden={!expanded}>{label}</span>
              </Link>
            );
          })}
          <button className="sidebar-link" type="button" aria-label="Notifications" title="Notifications">
            <Bell className="sidebar-icon sidebar-icon--notification" aria-hidden="true" strokeWidth={1.4} />
            <span className="sidebar-link-label" aria-hidden={!expanded}>Notifications</span>
          </button>
        </nav>
        <div className="sidebar-user-wrap">
          <Link
            className={`sidebar-link sidebar-user${pathname === "/account" || pathname.startsWith("/account/") ? " is-active" : ""}`}
            href="/account"
            aria-label="Account"
            aria-current={pathname === "/account" || pathname.startsWith("/account/") ? "page" : undefined}
            title={!expanded ? "Account" : undefined}
          >
            <UserRound className="sidebar-icon sidebar-icon--account" aria-hidden="true" strokeWidth={1.7} />
            <span className="sidebar-link-label" aria-hidden={!expanded}>Account</span>
          </Link>
          <div className="sidebar-logout-popup" role="menu">
            <button className="sidebar-logout-btn" type="button" onClick={signOut} role="menuitem">
              <LogOut aria-hidden="true" />
              Log out
            </button>
          </div>
        </div>
      </aside>

      <div className="app-main">
        {error ? <p className="shell-error" role="alert">{error}</p> : null}
        <main className="app-content">{children}</main>
      </div>
    </div>
  );
}
