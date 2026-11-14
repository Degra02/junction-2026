import { useState } from "react";
import { motion } from "motion/react";
import { GitCompareArrows, Globe2, ShieldCheck } from "lucide-react";
import { AnalysisInputForm, type PrefillValue } from "../components/AnalysisInputForm";
import { DemoPresets } from "../components/DemoPresets";
import type { DemoPreset } from "../data/presets";
import { GENTLE_SPRING } from "../lib/motion";

export type HomePageProps = Record<string, never>;

export function HomePage(_props: Readonly<HomePageProps>) {
  const [prefill, setPrefill] = useState<PrefillValue | null>(null);

  function handleSelectPreset(preset: DemoPreset) {
    setPrefill({
      value: preset.value,
      kind: preset.kind,
      nonce: Date.now(),
    });
  }

  return (
    <div className="py-4 sm:py-10 space-y-12">
      {/* Centered Focal Hero + Unified Omnibox */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={GENTLE_SPRING}
        className="max-w-[760px] mx-auto space-y-7"
      >
        <div className="text-center space-y-3.5 px-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full glass-pill text-xs font-medium text-[var(--fg-secondary)]">
            <span className="h-2 w-2 rounded-full bg-[var(--accent)] animate-pulse" />
            <span>Live Cross-Outlet Verification &amp; Coordination Detection</span>
          </div>

          <h1 className="text-3xl sm:text-4xl lg:text-[42px] font-bold tracking-tight leading-[1.12] text-[var(--fg-primary)] m-0">
            See how everyone else covered it—and how sure we are.
          </h1>

          <p className="text-sm sm:text-base text-[var(--fg-secondary)] leading-relaxed max-w-[56ch] mx-auto m-0">
            Paste any text or link. We search live multilingual coverage, check ClaimReview fact-checkers and domain registries, and compute transparent confidence scores backed by verbatim quotes.
          </p>
        </div>

        {/* Primary Unified Omnibox */}
        <AnalysisInputForm prefill={prefill} />

        {/* Compact Floating Case Pills */}
        <DemoPresets onSelectPreset={handleSelectPreset} />
      </motion.div>

      {/* Subtle Floating Trust Pillars (Calm, Non-Cluttered) */}
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ ...GENTLE_SPRING, delay: 0.08 }}
        className="max-w-[900px] mx-auto pt-4 grid grid-cols-1 sm:grid-cols-3 gap-3.5"
      >
        <div className="editorial-card rounded-2xl p-4 space-y-1.5">
          <div className="flex items-center gap-2 text-xs font-semibold text-[var(--fg-primary)]">
            <Globe2 className="h-4 w-4 text-[var(--accent)] shrink-0" aria-hidden="true" />
            <span>Live multi-source retrieval</span>
          </div>
          <p className="text-xs text-[var(--fg-secondary)] leading-relaxed m-0">
            Compares claims and emotional tone against peer outlets covering the exact same event across languages.
          </p>
        </div>

        <div className="editorial-card rounded-2xl p-4 space-y-1.5">
          <div className="flex items-center gap-2 text-xs font-semibold text-[var(--fg-primary)]">
            <GitCompareArrows className="h-4 w-4 text-[var(--indigo)] shrink-0" aria-hidden="true" />
            <span>Two calibrated dimensions</span>
          </div>
          <p className="text-xs text-[var(--fg-secondary)] leading-relaxed m-0">
            Separates manipulation inside the text from coordinated cross-domain copy networks and VIGINUM registries.
          </p>
        </div>

        <div className="editorial-card rounded-2xl p-4 space-y-1.5">
          <div className="flex items-center gap-2 text-xs font-semibold text-[var(--fg-primary)]">
            <ShieldCheck className="h-4 w-4 text-[var(--teal)] shrink-0" aria-hidden="true" />
            <span>Built against false alarms</span>
          </div>
          <p className="text-xs text-[var(--fg-secondary)] leading-relaxed m-0">
            Masks quotations in fact-checks, excludes Reuters/AP/ANSA wire syndication, and abstains when evidence is thin.
          </p>
        </div>
      </motion.div>
    </div>
  );
}
