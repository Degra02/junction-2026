import { Link } from "react-router-dom";
import * as HoverCard from "@radix-ui/react-hover-card";
import { Play } from "lucide-react";
import { DEMO_PRESETS, type DemoPreset } from "../data/presets";
import { cleanDomain } from "../lib/evidence";
import { SECTION_LABEL, buttonClass, tagClass } from "../lib/ui";
import { Favicon } from "./ui/Favicon";

export interface DemoPresetsProps {
  readonly onSelectPreset: (preset: DemoPreset) => void;
}

const SHORT_LABELS: Record<string, string> = {
  pk_de_002: "Portal Kombat network",
  fcd_de_002: "NASA climate claim",
  fc_de_005: "Fact-check of that claim",
  ansa_it: "ANSA wire copy",
  fcd_en_001: "Debunked viral report",
};

export function DemoPresets({ onSelectPreset }: Readonly<DemoPresetsProps>) {
  return (
    <section aria-label="Examples" className="space-y-3">
      <p className={`${SECTION_LABEL} text-center`}>Or try an example</p>
      <ul className="flex flex-wrap justify-center gap-2">
        {DEMO_PRESETS.map((preset) => {
          const label = SHORT_LABELS[preset.key] ?? preset.beat;
          const domain = preset.kind === "url" ? cleanDomain(preset.value) : "";
          const replayTo = `/analyses/${preset.replayAnalysisId}?replay=true`;

          return (
            <li key={preset.key}>
              <HoverCard.Root openDelay={250} closeDelay={100}>
                <HoverCard.Trigger asChild>
                  <div
                    data-spotlight
                    className="glass-pill rounded-lg h-8 inline-flex items-center overflow-hidden transition-colors hover:border-[var(--border-strong)]"
                  >
                    <button
                      type="button"
                      onClick={() => onSelectPreset(preset)}
                      className="h-full pl-2.5 pr-2 inline-flex items-center gap-2 text-[13px] text-[var(--fg-primary)] cursor-pointer"
                    >
                      {domain && <Favicon domain={domain} size={14} />}
                      {label}
                      <span className="font-mono-num text-[11px] uppercase text-[var(--fg-muted)]">
                        {preset.language}
                      </span>
                    </button>
                    <Link
                      to={replayTo}
                      aria-label={`Replay the stored run: ${label}`}
                      title="Replay the stored run"
                      className="h-full w-8 inline-flex items-center justify-center border-l border-[var(--border-subtle)] text-[var(--fg-muted)] hover:text-[var(--fg-primary)] hover:bg-[var(--bg-hover)] transition-colors"
                    >
                      <Play className="h-3 w-3 fill-current" aria-hidden="true" />
                    </Link>
                  </div>
                </HoverCard.Trigger>
                <HoverCard.Portal>
                  <HoverCard.Content
                    side="bottom"
                    sideOffset={8}
                    className="z-50 glass-popover rounded-xl p-4 w-80 space-y-3 outline-none"
                  >
                    <div className="flex items-center gap-2">
                      <span className={tagClass("neutral")}>{preset.beat}</span>
                      {domain && (
                        <span className="font-mono-num text-[11px] text-[var(--fg-muted)] truncate">
                          {domain}
                        </span>
                      )}
                    </div>
                    <p className="font-serif text-[15px] leading-snug text-[var(--fg-primary)]">
                      {preset.title}
                    </p>
                    <p className="text-[13px] leading-relaxed text-[var(--fg-secondary)]">
                      {preset.note}
                    </p>
                    <div className="flex items-center gap-2 pt-1">
                      <button
                        type="button"
                        onClick={() => onSelectPreset(preset)}
                        className={buttonClass("secondary", "sm")}
                      >
                        Use this input
                      </button>
                      <Link to={replayTo} className={buttonClass("primary", "sm")}>
                        <Play className="h-3 w-3 fill-current" aria-hidden="true" />
                        Replay run
                      </Link>
                    </div>
                  </HoverCard.Content>
                </HoverCard.Portal>
              </HoverCard.Root>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
