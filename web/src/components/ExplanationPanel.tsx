import { useState } from "react";
import { useNavigate } from "react-router-dom";
import * as Popover from "@radix-ui/react-popover";
import { Check, ChevronDown, Loader2 } from "lucide-react";
import { createAnalysis, describeError } from "../lib/api";
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
import { buttonClass, SECTION_LABEL } from "../lib/ui";
import { cn } from "../lib/utils";
import { CitationChip } from "./CitationChip";
import { Hint } from "./ui/Hint";

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
      setLangError(describeError(err));
    } finally {
      setSwitchingLang(false);
    }
  }

  if (!explanation || (!explanation.summary && explanation.reasons.length === 0)) {
    return null;
  }

  // The priors disclaimer becomes a footnote instead of part of the summary.
  const priorsMatch = explanation.summary.match(PRIORS_SENTENCE_REGEX);
  const priorsNote = priorsMatch?.[1]?.trim() ?? null;
  const cleanSummary = explanation.summary.replace(PRIORS_SENTENCE_REGEX, "").trim();

  return (
    <section aria-labelledby="findings-heading" className="editorial-card rounded-xl p-4 sm:p-5 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 id="findings-heading" className="text-sm font-medium text-[var(--fg-primary)]">
          Why
        </h2>

        <div className="flex items-center gap-1 -mr-2.5">
          {switchingLang && <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--fg-muted)]" aria-hidden="true" />}
          {canSwitchToContentLang && contentLang && (
            <Hint content={`Runs the analysis again with the summary in ${languageName(contentLang)} (about a minute).`}>
              <button
                type="button"
                disabled={switchingLang}
                onClick={() => void switchExplanationLanguage(contentLang)}
                className={buttonClass("ghost", "sm")}
              >
                Explain in {languageName(contentLang)}
              </button>
            </Hint>
          )}

          <Popover.Root>
            <Popover.Trigger asChild>
              <button
                type="button"
                disabled={switchingLang}
                aria-label="Summary language"
                className={buttonClass("ghost", "sm")}
              >
                <span className="font-mono-num uppercase">{currentExpLang}</span>
                <ChevronDown className="h-3 w-3" aria-hidden="true" />
              </button>
            </Popover.Trigger>
            <Popover.Portal>
              <Popover.Content
                align="end"
                sideOffset={6}
                className="z-50 glass-popover rounded-xl p-1 w-48 outline-none"
              >
                <div className={cn(SECTION_LABEL, "px-2 pt-1.5")}>Explain in</div>
                <p className="px-2 pb-1.5 text-[11px] text-[var(--fg-muted)]">Runs the analysis again.</p>
                {EXPLANATION_LANGUAGE_OPTIONS.map((opt) => {
                  const code = opt.code || "en";
                  const active = code === currentExpLang;
                  return (
                    <button
                      key={code}
                      type="button"
                      disabled={active}
                      aria-current={active ? "true" : undefined}
                      onClick={() => void switchExplanationLanguage(opt.code)}
                      className={cn(
                        "w-full flex items-center justify-between gap-2 px-2 h-7 rounded-md text-[13px] text-left transition-colors",
                        active
                          ? "text-[var(--fg-primary)] font-medium cursor-default"
                          : "text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] cursor-pointer",
                      )}
                    >
                      <span>{opt.label}</span>
                      {active && <Check className="h-3.5 w-3.5 text-[var(--accent)]" aria-hidden="true" />}
                    </button>
                  );
                })}
              </Popover.Content>
            </Popover.Portal>
          </Popover.Root>
        </div>
      </div>

      {langError && <p className="text-xs text-[var(--danger)]">{langError}</p>}

      {cleanSummary && (
        <p className="max-w-[68ch] font-serif text-[17px] leading-[1.6] text-pretty text-[var(--fg-primary)]">
          {cleanSummary}
        </p>
      )}

      {explanation.reasons.length > 0 && (
        <ol className="p-0 list-none">
          {explanation.reasons.map((reason, idx) => {
            const linkedEvidence = reason.evidence_ids
              .map((eid) => evidenceMap.get(eid))
              .filter((e): e is Evidence => e !== undefined);

            return (
              <li key={idx} className="flex items-baseline gap-3 py-3 border-t border-[var(--border-subtle)]">
                <span className="font-mono-num text-xs text-[var(--fg-muted)] shrink-0">
                  {String(idx + 1).padStart(2, "0")}
                </span>
                <div className="min-w-0 flex-1 space-y-2">
                  <p className="text-sm leading-relaxed text-[var(--fg-primary)]">{reason.text}</p>
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

      {priorsNote && <p className="text-xs text-[var(--fg-muted)]">{priorsNote}</p>}
    </section>
  );
}
