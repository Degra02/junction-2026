import { useState } from "react";
import { motion } from "motion/react";
import { AnalysisInputForm, type PrefillValue } from "../components/AnalysisInputForm";
import { DemoPresets } from "../components/DemoPresets";
import type { DemoPreset } from "../data/presets";
import { GENTLE_SPRING } from "../lib/motion";

export type HomePageProps = Record<string, never>;

const HEADLINE = "Check any story against the rest of the news.";

export function HomePage(_props: Readonly<HomePageProps>) {
  const [prefill, setPrefill] = useState<PrefillValue | null>(null);

  function handleSelectPreset(preset: DemoPreset) {
    setPrefill({ value: preset.value, kind: preset.kind, nonce: Date.now() });
  }

  return (
    <div className="max-w-[680px] mx-auto pt-[6vh] sm:pt-[10vh] pb-10 space-y-10">
      <div className="space-y-4 text-center">
        <h1 className="display text-[40px] sm:text-[54px] leading-[1.04] text-[var(--fg-primary)]">
          {HEADLINE.split(" ").map((word, i) => (
            <motion.span
              key={`${word}-${i}`}
              initial={{ opacity: 0, y: 8, filter: "blur(6px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)", transitionEnd: { filter: "none" } }}
              transition={{ ...GENTLE_SPRING, delay: 0.04 * i }}
              className="inline-block whitespace-pre"
            >
              {i === 0 ? word : ` ${word}`}
            </motion.span>
          ))}
        </h1>
        <motion.p
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...GENTLE_SPRING, delay: 0.35 }}
          className="text-[15px] text-[var(--fg-secondary)]"
        >
          Paste a link or text. Every score comes with its sources.
        </motion.p>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ ...GENTLE_SPRING, delay: 0.45 }}
        className="space-y-8"
      >
        <AnalysisInputForm prefill={prefill} />
        <DemoPresets onSelectPreset={handleSelectPreset} />
      </motion.div>
    </div>
  );
}
