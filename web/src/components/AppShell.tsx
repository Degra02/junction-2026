import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { BarChart3, Moon, Radar, SearchCheck, Sun } from "lucide-react";
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
        // Non-blocking status indicator
      });
    return () => controller.abort();
  }, []);

  const isMetrics = location.pathname.startsWith("/metrics");
  const isHome = location.pathname === "/";

  return (
    <div className="min-h-[100dvh] flex flex-col bg-[var(--bg-canvas)] text-[var(--fg-primary)]">
      <header className="sticky top-0 z-30 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)]/95 backdrop-blur-sm">
        <div className="mx-auto max-w-[1280px] px-3 sm:px-6 lg:px-8 h-14 flex items-center justify-between gap-2 sm:gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <Link
              to="/"
              className="flex items-center gap-2 min-w-0 text-[var(--fg-primary)] hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] rounded-md"
            >
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--accent)] text-white shrink-0">
                <Radar className="h-4 w-4" aria-hidden="true" />
              </span>
              <span className="font-bold tracking-tight text-sm sm:text-base truncate">
                Decode the Noise
              </span>
            </Link>
            <span className="hidden md:inline-block text-xs text-[var(--fg-muted)] border-l border-[var(--border-subtle)] pl-3 truncate">
              Context-aware propaganda &amp; coordination analysis
            </span>
          </div>

          <nav aria-label="Primary" className="flex items-center gap-1 sm:gap-2 shrink-0">
            <Link
              to="/"
              className={cn(
                "inline-flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-colors min-h-[36px]",
                isHome
                  ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                  : "text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)]",
              )}
            >
              <SearchCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>Analyse</span>
            </Link>

            <Link
              to="/metrics"
              className={cn(
                "inline-flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-colors min-h-[36px]",
                isMetrics
                  ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                  : "text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)]",
              )}
            >
              <BarChart3 className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>Metrics</span>
            </Link>

            {health && (
              <span
                title={`API status: ${health.status} · build ${health.pipeline_version}`}
                className="hidden lg:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] text-xs text-[var(--fg-muted)] font-mono-num"
              >
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    health.status === "ok" ? "bg-[var(--teal)]" : "bg-[var(--caution)]",
                  )}
                />
                {health.pipeline_version.slice(0, 12)}
              </span>
            )}

            <button
              type="button"
              onClick={toggleTheme}
              aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)] transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]"
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

      <main className="flex-1 mx-auto w-full max-w-[1280px] px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
        {children}
      </main>

      <footer className="border-t border-[var(--border-subtle)] bg-[var(--bg-surface)] mt-12">
        <div className="mx-auto max-w-[1280px] px-4 sm:px-6 lg:px-8 py-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs text-[var(--fg-muted)]">
          <p className="m-0">
            Evidence-first OSINT pipeline: confidence per dimension with verbatim source checks — never a binary “propaganda / not” verdict.
          </p>
          <div className="flex items-center gap-4 shrink-0">
            <Link to="/metrics" className="hover:text-[var(--fg-primary)] underline underline-offset-2">
              Evaluation &amp; FPR benchmark
            </Link>
            <a
              href="/api/docs"
              target="_blank"
              rel="noreferrer"
              className="hover:text-[var(--fg-primary)] underline underline-offset-2"
            >
              OpenAPI Spec
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
