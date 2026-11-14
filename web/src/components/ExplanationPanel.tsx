import { useState } from "react";
import { useNavigate } from "react-router-dom";
import * as Popover from "@radix-ui/react-popover";
import { Globe, Info, Loader2 } from "lucide-react";
import { createAnalysis } from "../lib/api";
import type {
  ContextItem,
  DocumentData,
  Evidence,
  Explanation,
  Input,
  Language,
  SourceProfile,
} from "../lib/contracts";
import { EXPLANATION_LANGUAGE_OPTIONS, languageName } from "../lib/labels";
import { CitationChip } from "./CitationChip";

export interface ExplanationPanelProps {
  readonly explanation: Explanation | null | undefined;
  readonly evidence: readonly Evidence[];
  readonly document: DocumentData | null | undefined;
  readonly context: readonly ContextItem[];
  readonly sources: readonly SourceProfile[];
  readonly input: Input;
  readonly detectedLanguage: Language | null | undefined;
  readonly activeEvidenceId: string | null;
  readonly onInspectEvidence: (evidenceId: string) => void;
}

const PRIORS_SENTENCE_REGEX =
  /\s*(These percentages are preliminary estimates[^.]*\.|Queste percentuali sono stime preliminari[^.]*\.|Diese Prozentsätze sind vorläufige Schätzungen[^.]*\.|Ces pourcentages sont des estimations préliminaires[^.]*\.|Estos porcentajes son estimaciones preliminares[^.]*\.|Estas percentagens são estimativas preliminares[^.]*\.|Te wartości procentowe są wstępnymi szacunkami[^.]*\.|Deze percentages zijn voorlopige schattingen[^.]*\.|Эти проценты являются предварительными оценками[^.]*\.|Ці відсотки є попередніми оцінками[^.]*\.)/i;

export function ExplanationPanel({
  explanation,
  evidence,
  document,
  context,
  sources,
  input,
  detectedLanguage,
  activeEvidenceId,
  onInspectEvidence,
}: Readonly<ExplanationPanelProps>) {
  const navigate = useNavigate();
  const [switchingLang, setSwitchingLang] = useState<boolean>(false);
  const [langError, setLangError] = useState<string | null>(null);

  const currentExpLang = (input.explanation_language || "en").toLowerCase();
  const contentLang = detectedLanguage?.code?.toLowerCase() ?? null;
  const canSwitchToContentLang = Boolean(contentLang && contentLang !== currentExpLang);

  const evidenceMap = new Map(evidence.map((e) => [e.id, e]));

  async function switchExplanationLanguage(nextLang: string) {
    setLangError(null);
    setSwitchingLang(true);
    try {
      const created = await createAnalysis({
        kind: input.kind,
        value: input.value,
        explanation_language: nextLang || null,
      });
      navigate(`/analyses/${created.id}`);
    } catch (err: unknown) {
      setLangError(
        err instanceof Error ? err.message : "Could not generate translated explanation.",
      );
    } finally {
      setSwitchingLang(false);
    }
  }

  if (!explanation || (!explanation.summary && explanation.reasons.length === 0)) {
    return null;
  }

  // Separate the boilerplate priors disclaimer into a calm footnote callout
  const priorsMatch = explanation.summary.match(PRIORS_SENTENCE_REGEX);
  const priorsNote = priorsMatch?.[1]?.trim() ?? null;
  const cleanSummary = explanation.summary.replace(PRIORS_SENTENCE_REGEX, "").trim();

  return (
    <section
      aria-labelledby="findings-heading"
      className="editorial-card rounded-3xl p-5 sm:p-7 space-y-5"
    >
      {/* Header + Compact Language Pill */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2
          id="findings-heading"
          className="text-base font-bold tracking-tight text-[var(--fg-primary)] m-0"
        >
          Key findings &amp; verified evidence
        </h2>

        <div className="flex flex-wrap items-center gap-2">
          {canSwitchToContentLang && contentLang && (
            <button
              type="button"
              disabled={switchingLang}
              onClick={() => void switchExplanationLanguage(contentLang)}
              className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full bg-[var(--accent-soft)] border border-[var(--accent-border)] text-xs font-medium text-[var(--accent)] hover:opacity-90 disabled:opacity-50 cursor-pointer"
            >
              {switchingLang ? (
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
              ) : (
                <Globe className="h-3 w-3" aria-hidden="true" />
              )}
              <span>Read in {languageName(contentLang)}</span>
            </button>
          )}

          <Popover.Root>
            <Popover.Trigger asChild>
              <button
                type="button"
                disabled={switchingLang}
                className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full bg-[var(--bg-subtle)] border border-[var(--border-subtle)] text-xs font-medium text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] cursor-pointer"
              >
                <Globe className="h-3 w-3" aria-hidden="true" />
                <span className="font-mono-num uppercase">{currentExpLang}</span>
              </button>
            </Popover.Trigger>
            <Popover.Portal>
              <Popover.Content
                align="end"
                sideOffset={6}
                className="z-50 glass-popover rounded-2xl p-2 w-52 space-y-0.5 outline-none"
              >
                <div className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--fg-muted)]">
                  Summary language
                </div>
                {EXPLANATION_LANGUAGE_OPTIONS.map((opt) => {
                  const code = opt.code || "en";
                  const active = code === currentExpLang;
                  return (
                    <button
                      key={code}
                      type="button"
                      onClick={() => void switchExplanationLanguage(opt.code)}
                      className={`w-full text-left px-2.5 py-1.5 rounded-xl text-xs transition-colors cursor-pointer ${
                        active
                          ? "bg-[var(--accent-soft)] text-[var(--accent)] font-semibold"
                          : "text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)]/80"
                      }`}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </Popover.Content>
            </Popover.Portal>
          </Popover.Root>
        </div>
      </div>

      {langError && (
        <p className="text-xs text-[var(--danger)] m-0">{langError}</p>
      )}

      {/* Executive Summary */}
      {cleanSummary && (
        <p className="text-sm sm:text-[15px] leading-relaxed text-[var(--fg-primary)] m-0 max-w-[75ch]">
          {cleanSummary}
        </p>
      )}

      {/* Numbered Reasons with Floating Publisher/Source HoverCard Chips */}
      {explanation.reasons.length > 0 && (
        <ol className="space-y-3.5 list-none p-0 m-0 pt-1">
          {explanation.reasons.map((reason, idx) => {
            const linkedEvidence = reason.evidence_ids
              .map((eid) => evidenceMap.get(eid))
              .filter((e): e is Evidence => e !== undefined);

            return (
              <li
                key={idx}
                className="flex items-start gap-3 rounded-2xl bg-[var(--bg-canvas)] border border-[var(--border-subtle)] p-3.5 sm:p-4"
              >
                <span className="h-6 w-6 rounded-full bg-[var(--accent-soft)] text-[var(--accent)] font-mono-num text-xs font-bold inline-flex items-center justify-center shrink-0 mt-0.5">
                  {idx + 1}
                </span>

                <div className="space-y-2 min-w-0 flex-1">
                  <p className="text-xs sm:text-sm leading-relaxed text-[var(--fg-primary)] m-0">
                    {reason.text}
                  </p>

                  {linkedEvidence.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      {linkedEvidence.map((ev) => (
                        <CitationChip
                          key={ev.id}
                          evidence={ev}
                          document={document}
                          context={context}
                          sources={sources}
                          active={activeEvidenceId === ev.id}
                          onInspect={onInspectEvidence}
                        />
                      ))}
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}

      {/* Subtle Methodology Footnote for Uncalibrated Priors */}
      {priorsNote && (
        <div className="pt-3 border-t border-[var(--border-subtle)]/70 flex items-start gap-2 text-xs text-[var(--fg-muted)]">
          <Info className="h-3.5 w-3.5 text-[var(--caution)] shrink-0 mt-0.5" aria-hidden="true" />
          <span>{priorsNote}</span>
        </div>
      )}
    </section>
  );
}
