import { Link } from "react-router-dom";
import * as HoverCard from "@radix-ui/react-hover-card";
import { ArrowUpLeft, Play, Sparkles } from "lucide-react";
import { DEMO_PRESETS, type DemoPreset } from "../data/presets";
import { cleanDomain } from "../lib/evidence";

export interface DemoPresetsProps {
  readonly onSelectPreset: (preset: DemoPreset) => void;
}

const SHORT_PILL_LABELS: Record<string, string> = {
  pk_de_002: "Portal Kombat network",
  fcd_de_002: "NASA climate claim",
  fc_de_005: "BR24 fact-check (hard neg)",
  ansa_it: "ANSA wire dispatch",
  fcd_en_001: "Debunked viral report",
};

export function DemoPresets({ onSelectPreset }: Readonly<DemoPresetsProps>) {
  return (
    <section aria-label="Documented example cases" className="space-y-2.5">
      <div className="flex items-center justify-center gap-1.5 text-xs text-[var(--fg-muted)]">
        <Sparkles className="h-3.5 w-3.5 text-[var(--accent)]" aria-hidden="true" />
        <span>Try a documented case (hover to preview, click to load or replay live):</span>
      </div>

      <div className="flex flex-wrap items-center justify-center gap-2">
        {DEMO_PRESETS.map((preset) => {
          const shortName = SHORT_PILL_LABELS[preset.key] ?? preset.beat;
          const domain = preset.kind === "url" ? cleanDomain(preset.value) : null;

          return (
            <HoverCard.Root key={preset.key} openDelay={140} closeDelay={120}>
              <HoverCard.Trigger asChild>
                <div className="glass-pill rounded-full pl-3 pr-1.5 py-1 inline-flex items-center gap-2 hover:border-[var(--accent-border)] transition-colors">
                  <button
                    type="button"
                    onClick={() => onSelectPreset(preset)}
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--fg-primary)] hover:text-[var(--accent)] transition-colors cursor-pointer"
                  >
                    <span className="font-mono-num text-[10px] uppercase px-1.5 py-0.5 rounded-full bg-[var(--bg-subtle)] text-[var(--fg-muted)]">
                      {preset.language}
                    </span>
                    <span>{shortName}</span>
                  </button>

                  <Link
                    to={`/analyses/${preset.replayAnalysisId}?replay=true`}
                    title="Replay live pipeline step-by-step"
                    aria-label={`Replay live analysis for ${shortName}`}
                    className="h-6 w-6 rounded-full bg-[var(--accent-soft)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-white inline-flex items-center justify-center transition-colors"
                  >
                    <Play className="h-3 w-3 fill-current" aria-hidden="true" />
                  </Link>
                </div>
              </HoverCard.Trigger>

              <HoverCard.Portal>
                <HoverCard.Content
                  side="bottom"
                  align="center"
                  sideOffset={10}
                  className="z-50 glass-popover rounded-2xl p-4 w-80 sm:w-96 space-y-3 outline-none"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="px-2 py-0.5 rounded-full bg-[var(--accent-soft)] border border-[var(--accent-border)] text-[11px] font-semibold text-[var(--accent)]">
                      {preset.beat}
                    </span>
                    {domain && (
                      <span className="font-mono-num text-[11px] text-[var(--fg-muted)] truncate">
                        {domain}
                      </span>
                    )}
                  </div>

                  <div className="space-y-1">
                    <h3 className="text-xs font-bold text-[var(--fg-primary)] leading-snug m-0">
                      {preset.title}
                    </h3>
                    <p className="text-xs text-[var(--fg-secondary)] leading-relaxed m-0">
                      {preset.note}
                    </p>
                  </div>

                  <div className="pt-2 border-t border-[var(--border-subtle)]/80 flex items-center justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => onSelectPreset(preset)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-[var(--border-strong)] bg-[var(--bg-surface)] text-xs font-medium text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)] transition-colors cursor-pointer"
                    >
                      <ArrowUpLeft className="h-3.5 w-3.5" aria-hidden="true" />
                      <span>Paste in box</span>
                    </button>

                    <Link
                      to={`/analyses/${preset.replayAnalysisId}?replay=true`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[var(--accent)] text-white text-xs font-semibold hover:bg-[var(--accent-hover)] transition-colors"
                    >
                      <Play className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
                      <span>Replay step-by-step</span>
                    </Link>
                  </div>
                </HoverCard.Content>
              </HoverCard.Portal>
            </HoverCard.Root>
          );
        })}
      </div>
    </section>
  );
}
