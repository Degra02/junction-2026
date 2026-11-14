import { useState } from "react";
import { Link } from "react-router-dom";
import { GitCompareArrows, Quote, Scale, ShieldCheck } from "lucide-react";
import { AnalysisInputForm, type PrefillValue } from "../components/AnalysisInputForm";
import { DemoPresets } from "../components/DemoPresets";
import type { DemoPreset } from "../data/presets";

export type HomePageProps = Record<string, never>;

export function HomePage(_props: Readonly<HomePageProps>) {
  const [prefill, setPrefill] = useState<PrefillValue | null>(null);

  function handleSelectPreset(preset: DemoPreset) {
    setPrefill({
      value: preset.value,
      kind: preset.kind,
      nonce: Date.now(),
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <div className="space-y-10">
      {/* Asymmetric Editorial Hero + Input Composer */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8 items-start">
        <div className="lg:col-span-5 space-y-5 pt-1">
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-xs font-medium text-[var(--fg-secondary)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
            <span>Live multi-source OSINT verification</span>
          </div>

          <h1 className="text-2xl sm:text-3xl lg:text-[34px] font-bold tracking-tight leading-[1.16] text-[var(--fg-primary)] m-0">
            Paste a link or claim. See how everyone else covered it, what’s been copied, and how sure we are.
          </h1>

          <p className="text-sm sm:text-[15px] leading-relaxed text-[var(--fg-secondary)] m-0 max-w-[58ch]">
            A language model’s opinion of a text alone is not evidence. We retrieve live coverage across languages, cluster articles covering the same event, check ClaimReview fact-checkers and domain registries, and report separate confidence scores with every source linked.
          </p>

          <dl className="space-y-3 pt-2 border-t border-[var(--border-subtle)] m-0">
            <div className="flex items-start gap-3">
              <GitCompareArrows className="h-4 w-4 text-[var(--accent)] shrink-0 mt-0.5" aria-hidden="true" />
              <div className="text-xs leading-relaxed">
                <dt className="font-semibold text-[var(--fg-primary)] inline">
                  Two separate dimensions:{" "}
                </dt>
                <dd className="inline text-[var(--fg-secondary)] m-0">
                  manipulation in the content itself (persuasion techniques, peer-relative tone, contradicted claims) vs. coordinated cross-outlet campaigns (copied passages, shared tracking IDs, VIGINUM networks).
                </dd>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <ShieldCheck className="h-4 w-4 text-[var(--teal)] shrink-0 mt-0.5" aria-hidden="true" />
              <div className="text-xs leading-relaxed">
                <dt className="font-semibold text-[var(--fg-primary)] inline">
                  Built against false positives:{" "}
                </dt>
                <dd className="inline text-[var(--fg-secondary)] m-0">
                  quotations are masked so fact-checks quoting a hoax stay low; Reuters/AP/AFP/ANSA/dpa wire syndication is excluded from copy networks.
                </dd>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <Quote className="h-4 w-4 text-[var(--fg-muted)] shrink-0 mt-0.5" aria-hidden="true" />
              <div className="text-xs leading-relaxed">
                <dt className="font-semibold text-[var(--fg-primary)] inline">
                  No verdict stamps, verbatim quotes only:{" "}
                </dt>
                <dd className="inline text-[var(--fg-secondary)] m-0">
                  every quotation is verified code-point by code-point against the sources; thin context abstains with “Not enough evidence”.
                </dd>
              </div>
            </div>
          </dl>

          <div className="pt-1">
            <Link
              to="/metrics"
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--accent)] hover:underline"
            >
              <Scale className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Inspect precision, hard-negative FPRs &amp; Wilson 95% intervals</span>
            </Link>
          </div>
        </div>

        <div className="lg:col-span-7">
          <AnalysisInputForm prefill={prefill} />
        </div>
      </div>

      {/* Documented real cases */}
      <DemoPresets onSelectPreset={handleSelectPreset} />
    </div>
  );
}
