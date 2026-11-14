import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import * as Tooltip from "@radix-ui/react-tooltip";
import { BarChart3, Moon, Radar, Search, Sun } from "lucide-react";
import { getHealth } from "../lib/api";
import type { Health } from "../lib/contracts";
import { cn } from "../lib/utils";
import { useTheme } from "../hooks/useTheme";

export interface AppShellProps {
  readonly children: ReactNode;
}

export function AppShell({ children }: Readonly<AppShellProps>) {
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then(setHealth)
      .catch(() => {
        // Silent when running frontend standalone without backend
      });
    return () => controller.abort();
  }, []);

  const isMetrics = location.pathname.startsWith("/metrics");
  const isHome = location.pathname === "/";

  return (
    <Tooltip.Provider delayDuration={180}>
      <div className="min-h-[100dvh] flex flex-col bg-[var(--bg-canvas)] canvas-ambient text-[var(--fg-primary)] selection:bg-[var(--accent-soft)] selection:text-[var(--accent)]">
        {/* Floating Liquid Glass Top Navigation Bar */}
        <header className="sticky top-0 z-40 px-3 sm:px-6 pt-3 pb-2 pointer-events-none">
          <div className="mx-auto max-w-[1080px] glass-pill rounded-2xl px-3.5 sm:px-4 h-12 flex items-center justify-between gap-3 pointer-events-auto">
            <div className="flex items-center gap-2.5 min-w-0">
              <Link
                to="/"
                className="inline-flex items-center gap-2.5 text-sm font-bold tracking-tight text-[var(--fg-primary)] hover:opacity-85 transition-opacity truncate"
              >
                <span className="h-7 w-7 rounded-xl bg-[var(--accent)] text-white inline-flex items-center justify-center shadow-xs shrink-0">
                  <Radar className="h-4 w-4" aria-hidden="true" />
                </span>
                <span className="truncate">Decode the Noise</span>
              </Link>

              {health && (
                <Tooltip.Root>
                  <Tooltip.Trigger asChild>
                    <span
                      tabIndex={0}
                      className="hidden sm:inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-[var(--bg-subtle)]/80 border border-[var(--border-subtle)] text-[11px] font-mono-num text-[var(--fg-muted)] cursor-default"
                    >
                      <span
                        className={cn(
                          "h-1.5 w-1.5 rounded-full",
                          health.status === "ok" ? "bg-[var(--teal)]" : "bg-[var(--caution)]",
                        )}
                      />
                      <span>{health.pipeline_version.slice(0, 10)}</span>
                    </span>
                  </Tooltip.Trigger>
                  <Tooltip.Portal>
                    <Tooltip.Content
                      sideOffset={8}
                      className="z-50 glass-popover rounded-xl px-3 py-2 text-xs text-[var(--fg-primary)] max-w-xs"
                    >
                      API {health.status === "ok" ? "online" : "degraded"} · build{" "}
                      <code className="font-mono-num">{health.pipeline_version}</code>
                    </Tooltip.Content>
                  </Tooltip.Portal>
                </Tooltip.Root>
              )}
            </div>

            <nav aria-label="Primary" className="flex items-center gap-1 sm:gap-1.5 shrink-0">
              <Link
                to="/"
                aria-current={isHome ? "page" : undefined}
                className={cn(
                  "inline-flex items-center gap-1.5 h-8 px-3 rounded-xl text-xs font-medium transition-colors",
                  isHome
                    ? "bg-[var(--accent-soft)] text-[var(--accent)] font-semibold"
                    : "text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)]/70",
                )}
              >
                <Search className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Investigate</span>
              </Link>

              <Link
                to="/metrics"
                aria-current={isMetrics ? "page" : undefined}
                className={cn(
                  "inline-flex items-center gap-1.5 h-8 px-3 rounded-xl text-xs font-medium transition-colors",
                  isMetrics
                    ? "bg-[var(--accent-soft)] text-[var(--accent)] font-semibold"
                    : "text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)]/70",
                )}
              >
                <BarChart3 className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Benchmarks</span>
              </Link>

              <div className="h-4 w-px bg-[var(--border-subtle)] mx-0.5" aria-hidden="true" />

              <button
                type="button"
                onClick={toggleTheme}
                aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
                title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
                className="inline-flex items-center justify-center h-8 w-8 rounded-xl text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)]/70 transition-colors cursor-pointer"
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

        <main className="flex-1 mx-auto w-full max-w-[1080px] px-4 sm:px-6 lg:px-8 py-6 sm:py-10">
          {children}
        </main>

        <footer className="mt-auto py-6 px-4 sm:px-6">
          <div className="mx-auto max-w-[1080px] pt-5 border-t border-[var(--border-subtle)]/70 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-xs text-[var(--fg-muted)]">
            <span>
              Evidence-first verification — confidence scores reflect measured alignment with documented signals, never ground-truth labels.
            </span>
            <Link
              to="/metrics"
              className="font-medium text-[var(--fg-secondary)] hover:text-[var(--accent)] transition-colors shrink-0"
            >
              Methodology &amp; False-Positive Rates →
            </Link>
          </div>
        </footer>
      </div>
    </Tooltip.Provider>
  );
}
