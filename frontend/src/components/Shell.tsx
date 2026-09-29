"use client";

import clsx from "clsx";
import { Cpu, FlaskConical, FolderKanban, LogOut, Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import { APP_NAME } from "@/lib/format";
import { useSession } from "@/lib/session";
import { Wordmark } from "./brand";
import { ErrorNote, Spinner } from "./ui";

const NAV = [
  { href: "/", label: "Projects", icon: FolderKanban },
  { href: "/materials", label: "Materials", icon: FlaskConical },
  { href: "/workers", label: "Compute", icon: Cpu },
];

const THEME_EVENT = "autoeng-theme";

function subscribeTheme(cb: () => void) {
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  mq.addEventListener("change", cb);
  window.addEventListener(THEME_EVENT, cb);
  return () => {
    mq.removeEventListener("change", cb);
    window.removeEventListener(THEME_EVENT, cb);
  };
}

function currentTheme(): "light" | "dark" {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function ThemeToggle() {
  const theme = useSyncExternalStore(subscribeTheme, currentTheme, () => "dark" as const);
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("autoeng.theme", next);
    } catch {
      /* no storage */
    }
    window.dispatchEvent(new Event(THEME_EVENT));
  };
  return (
    <button type="button" onClick={toggle} aria-label="Toggle colour theme" className="text-ink-3 transition-colors hover:text-ink">
      {theme === "dark" ? <Sun className="size-4" strokeWidth={1.5} /> : <Moon className="size-4" strokeWidth={1.5} />}
    </button>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const { ready, user, health, error, signOut } = useSession();
  const pathname = usePathname();
  const router = useRouter();
  const onLogin = pathname === "/login";
  const fullBleed = onLogin || pathname === "/";

  useEffect(() => {
    if (ready && !user && !onLogin && !error) router.replace("/login");
  }, [ready, user, onLogin, error, router]);

  return (
    <div className="flex min-h-screen flex-col">
      {!onLogin && (
        <header className="sticky top-0 z-30 border-b border-line bg-page/80 backdrop-blur-xl">
          <div className="mx-auto flex h-16 max-w-[1680px] items-center gap-10 px-6 lg:px-10">
            <Link href="/" className="text-ink" aria-label={`${APP_NAME} home`}>
              <Wordmark />
            </Link>
            {user && (
              <nav className="flex items-center gap-7">
                {NAV.map((n) => {
                  const active = n.href === "/" ? pathname === "/" || pathname.startsWith("/projects") : pathname.startsWith(n.href);
                  return (
                    <Link
                      key={n.href}
                      href={n.href}
                      className={clsx(
                        "relative inline-flex items-center gap-2 py-5 font-display text-[13px] font-medium uppercase tracking-[0.2em] transition-colors",
                        active ? "text-ink" : "text-ink-3 hover:text-ink-2",
                      )}
                    >
                      <n.icon className="size-3.5 sm:hidden" aria-hidden />
                      <span className="hidden sm:inline">{n.label}</span>
                      {active && <span className="absolute inset-x-0 -bottom-px h-px bg-ink" aria-hidden />}
                    </Link>
                  );
                })}
              </nav>
            )}
            <div className="ml-auto flex items-center gap-5">
              {health && (
                <span className="eyebrow hidden items-center gap-2 lg:inline-flex" title="Compute available to this server">
                  <span className="inline-block size-1.5 rounded-full" style={{ background: "var(--good)" }} aria-hidden />
                  {health.compute.gpu_available ? health.compute.gpu_device?.replace("NVIDIA GeForce ", "") : "CPU"}
                </span>
              )}
              <ThemeToggle />
              {user && !health?.auth_disabled && (
                <button
                  type="button"
                  onClick={() => signOut().then(() => router.replace("/login"))}
                  className="inline-flex items-center gap-2 font-display text-[12px] font-medium uppercase tracking-[0.18em] text-ink-3 hover:text-ink"
                >
                  <LogOut className="size-3.5" aria-hidden />
                  <span className="hidden md:inline">{user.name || "Sign out"}</span>
                </button>
              )}
            </div>
          </div>
        </header>
      )}
      <main className={clsx("w-full flex-1", !fullBleed && "mx-auto max-w-[1680px] px-6 py-8 lg:px-10")}>
        {error && (
          <div className="mx-auto max-w-3xl p-6">
            <ErrorNote error={error} />
          </div>
        )}
        {!ready && (
          <div className="p-10">
            <Spinner label="Connecting" />
          </div>
        )}
        {ready && (user || onLogin) && children}
      </main>
      {!onLogin && (
        <footer className="border-t border-line">
          <div className="mx-auto flex max-w-[1680px] flex-wrap items-center justify-between gap-3 px-6 py-6 lg:px-10">
            <span className="eyebrow">{APP_NAME}</span>
            <span className="text-xs text-ink-3">
              Engineering estimates from physics models with stated uncertainty. Not a safety certification.
            </span>
          </div>
        </footer>
      )}
    </div>
  );
}
