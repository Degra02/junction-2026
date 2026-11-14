import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import * as Tooltip from "@radix-ui/react-tooltip";
import { Moon, Sun } from "lucide-react";
import { getHealth } from "../lib/api";
import type { Health } from "../lib/contracts";
import { buttonClass } from "../lib/ui";
import { cn } from "../lib/utils";
import { usePointerEffects } from "../hooks/usePointerEffects";
import { useTheme } from "../hooks/useTheme";

export interface AppShellProps {
  readonly children: ReactNode;
}

/** Bars of rising height: signal out of noise. */
function LogoMark() {
  return (
    <svg viewBox="0 0 20 20" className="h-5 w-5" aria-hidden="true">
      <rect x="2" y="9" width="2.2" height="2" rx="1.1" fill="currentColor" opacity="0.35" />
      <rect x="6" y="7.5" width="2.2" height="5" rx="1.1" fill="currentColor" opacity="0.5" />
      <rect x="10" y="4.5" width="2.2" height="11" rx="1.1" fill="currentColor" />
      <rect x="14" y="7.5" width="2.2" height="5" rx="1.1" fill="currentColor" opacity="0.5" />
    </svg>
  );
}

const NAV_LINK =
  "h-8 px-2.5 inline-flex items-center rounded-lg text-[13px] font-medium transition-colors";

export function AppShell({ children }: Readonly<AppShellProps>) {
  const { theme, toggleTheme } = useTheme();
  const [health, setHealth] = useState<Health | null>(null);
  const [scrolled, setScrolled] = useState(false);
  const backdropRef = useRef<HTMLDivElement | null>(null);
  usePointerEffects(backdropRef);

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then(setHealth)
      .catch(() => {
        // The UI also runs without a backend (mock server, static preview).
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <Tooltip.Provider delayDuration={200}>
      <div className="relative isolate min-h-[100dvh] flex flex-col text-[var(--fg-primary)]">
        <div ref={backdropRef} className="app-backdrop" aria-hidden="true">
          <div className="app-backdrop__glow" />
          <div className="app-backdrop__cursor" />
          <div className="app-backdrop__grain" />
        </div>

        <header
          className={cn(
            "sticky top-0 z-40 border-b transition-[background-color,border-color] duration-200",
            scrolled
              ? "border-[var(--border-subtle)] bg-[var(--bg-elevated)] backdrop-blur-xl backdrop-saturate-150"
              : "border-transparent bg-transparent",
          )}
        >
          <div className="mx-auto max-w-[1120px] h-14 px-4 sm:px-6 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <Link
                to="/"
                className="inline-flex items-center gap-2 text-[var(--fg-primary)] hover:opacity-80 transition-opacity"
              >
                <LogoMark />
                <span className="font-serif text-[17px] font-medium tracking-tight whitespace-nowrap">Decode the Noise</span>
              </Link>

              {health && (
                <Tooltip.Root>
                  <Tooltip.Trigger asChild>
                    <span
                      tabIndex={0}
                      className="hidden sm:inline-flex items-center gap-1.5 text-[11px] font-mono-num text-[var(--fg-muted)] cursor-default"
                    >
                      <span
                        className={cn(
                          "h-1.5 w-1.5 rounded-full",
                          health.status === "ok" ? "bg-[var(--teal)]" : "bg-[var(--caution)]",
                        )}
                      />
                      {health.pipeline_version.slice(0, 11)}
                    </span>
                  </Tooltip.Trigger>
                  <Tooltip.Portal>
                    <Tooltip.Content
                      sideOffset={8}
                      className="z-50 glass-popover rounded-lg px-2.5 py-1.5 text-xs text-[var(--fg-primary)]"
                    >
                      API {health.status === "ok" ? "online" : "degraded"} ·{" "}
                      <code className="font-mono-num">{health.pipeline_version}</code>
                    </Tooltip.Content>
                  </Tooltip.Portal>
                </Tooltip.Root>
              )}
            </div>

            <nav aria-label="Primary" className="flex items-center gap-0.5">
              <NavLink
                to="/"
                end
                className={({ isActive }) =>
                  cn(
                    NAV_LINK,
                    isActive
                      ? "text-[var(--fg-primary)]"
                      : "text-[var(--fg-muted)] hover:text-[var(--fg-primary)]",
                  )
                }
              >
                Analyze
              </NavLink>
              <NavLink
                to="/metrics"
                className={({ isActive }) =>
                  cn(
                    NAV_LINK,
                    isActive
                      ? "text-[var(--fg-primary)]"
                      : "text-[var(--fg-muted)] hover:text-[var(--fg-primary)]",
                  )
                }
              >
                Benchmarks
              </NavLink>
              <button
                type="button"
                onClick={toggleTheme}
                aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
                className={buttonClass("ghost", "icon", "ml-1")}
              >
                {theme === "dark" ? (
                  <Sun className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <Moon className="h-4 w-4" aria-hidden="true" />
                )}
              </button>
            </nav>
          </div>
        </header>

        <main className="flex-1 mx-auto w-full max-w-[1120px] px-4 sm:px-6 py-8 sm:py-12">
          {children}
        </main>

        <footer className="mx-auto w-full max-w-[1120px] px-4 sm:px-6 pb-8">
          <div className="pt-5 border-t border-[var(--border-subtle)] flex flex-wrap items-center justify-between gap-2 text-xs text-[var(--fg-muted)]">
            <span>Scores are confidences from documented signals, not verdicts.</span>
            <Link to="/metrics" className="hover:text-[var(--fg-primary)] transition-colors">
              How accurate is it? →
            </Link>
          </div>
        </footer>
      </div>
    </Tooltip.Provider>
  );
}
