import { Link } from "react-router-dom";
import { Play, ArrowUpLeft } from "lucide-react";
import { DEMO_PRESETS, type DemoPreset } from "../data/presets";

export interface DemoPresetsProps {
  readonly onSelectPreset: (preset: DemoPreset) => void;
}

export function DemoPresets({ onSelectPreset }: Readonly<DemoPresetsProps>) {
  return (
    <section aria-labelledby="presets-heading" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="presets-heading" className="text-sm font-semibold text-[var(--fg-primary)]">
          Documented real-world cases
        </h2>
        <p className="text-xs text-[var(--fg-muted)] m-0">
          Replay stored VPS runs step-by-step with zero scraper wait, or load into the input box above.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {DEMO_PRESETS.map((preset, idx) => (
          <div
            key={preset.key}
            className={
              idx === 0
                ? "md:col-span-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
                : "rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 flex flex-col justify-between gap-3"
            }
          >
            <div className="space-y-1.5 min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-[var(--bg-subtle)] text-[11px] font-medium text-[var(--fg-secondary)]">
                  {preset.beat}
                </span>
                <span className="inline-flex items-center px-1.5 py-0.5 rounded border border-[var(--border-subtle)] font-mono-num text-[11px] uppercase text-[var(--fg-muted)]">
                  {preset.language}
                </span>
                <span className="text-[11px] text-[var(--fg-muted)] font-mono-num">
                  {preset.kind === "url" ? "URL" : "Text"}
                </span>
              </div>
              <h3 className="text-sm font-semibold text-[var(--fg-primary)] leading-snug">
                {preset.title}
              </h3>
              <p className="text-xs text-[var(--fg-secondary)] leading-relaxed m-0">
                {preset.note}
              </p>
            </div>

            <div className="flex items-center gap-2 shrink-0 pt-1 sm:pt-0">
              <Link
                to={`/analyses/${preset.replayAnalysisId}?replay=true`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--accent-soft)] border border-[var(--accent-border)] text-xs font-semibold text-[var(--accent)] hover:opacity-90 transition-opacity min-h-[34px]"
              >
                <Play className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Replay run</span>
              </Link>
              <button
                type="button"
                onClick={() => onSelectPreset(preset)}
                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-surface)] text-xs font-medium text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)] transition-colors cursor-pointer min-h-[34px]"
              >
                <ArrowUpLeft className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Prefill</span>
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
