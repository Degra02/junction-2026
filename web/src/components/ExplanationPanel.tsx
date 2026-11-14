import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Globe, Sparkles } from "lucide-react";
import { createAnalysis } from "../lib/api";
import type { Evidence, Explanation, Input, Language } from "../lib/contracts";
import { EXPLANATION_LANGUAGE_OPTIONS, languageName } from "../lib/labels";
import { cn } from "../lib/utils";

export interface ExplanationPanelProps {
  readonly explanation: Explanation | null | undefined;
  readonly evidence: readonly Evidence[];
  readonly input: Input;
  readonly detectedLanguage: Language | null | undefined;
  readonly activeEvidenceId: string | null;
  readonly onSelectEvidence: (evidenceId: string) => void;
  readonly isPending: boolean;
}

export function ExplanationPanel({
  explanation,
  evidence,
  input,
  detectedLanguage,
  activeEvidenceId,
  onSelectEvidence,
  isPending,
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
      setLangError(err instanceof Error ? err.message : "Could not request translated explanation.");
    } finally {
      setSwitchingLang(false);
    }
  }

  return (
    <section
      aria-labelledby="explanation-heading"
      className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 space-y-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-[var(--border-subtle)]">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-[var(--accent)]" aria-hidden="true" />
          <h2
            id="explanation-heading"
            className="text-base font-bold tracking-tight text-[var(--fg-primary)] m-0"
          >
            Evidence summary &amp; key reasons
          </h2>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {canSwitchToContentLang && contentLang && (
            <button
              type="button"
              disabled={switchingLang}
              onClick={() => switchExplanationLanguage(contentLang)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[var(--accent-soft)] border border-[var(--accent-border)] text-xs font-semibold text-[var(--accent)] hover:opacity-90 disabled:opacity-50 cursor-pointer"
            >
              <Globe className="h-3.5 w-3.5" aria-hidden="true" />
              <span>
                {switchingLang
                  ? "Switching…"
                  : `Explain in ${languageName(contentLang)} (${contentLang})`}
              </span>
            </button>
          )}

          <label className="inline-flex items-center gap-1.5 text-xs text-[var(--fg-muted)]">
            <span className="sr-only">Explanation language</span>
            <select
              aria-label="Explanation language"
              disabled={switchingLang}
              value={
                EXPLANATION_LANGUAGE_OPTIONS.some((o) => (o.code || "en") === currentExpLang)
                  ? currentExpLang === "en"
                    ? ""
                    : currentExpLang
                  : currentExpLang
              }
              onChange={(e) => switchExplanationLanguage(e.target.value)}
              className="h-8 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-2 text-xs text-[var(--fg-secondary)] focus:border-[var(--accent)] focus:outline-none"
            >
              {EXPLANATION_LANGUAGE_OPTIONS.map((opt) => (
                <option key={opt.code || "en"} value={opt.code}>
                  {opt.label}
                </option>
              ))}
              {!EXPLANATION_LANGUAGE_OPTIONS.some((o) => (o.code || "en") === currentExpLang) && (
                <option value={currentExpLang}>
                  {languageName(currentExpLang)} ({currentExpLang})
                </option>
              )}
            </select>
          </label>
        </div>
      </div>

      {langError && (
        <p role="alert" className="text-xs text-[var(--danger)] m-0">
          {langError}
        </p>
      )}

      {isPending && !explanation ? (
        <div className="space-y-3 py-1" aria-busy="true">
          <div className="h-4 w-5/6 rounded bg-[var(--bg-subtle)] animate-pulse" />
          <div className="h-4 w-3/4 rounded bg-[var(--bg-subtle)] animate-pulse" />
          <div className="h-12 w-full rounded-lg bg-[var(--bg-subtle)] animate-pulse mt-2" />
        </div>
      ) : !explanation ? (
        <p className="text-sm text-[var(--fg-muted)] m-0">
          No explanation generated for this analysis.
        </p>
      ) : (
        <div className="space-y-4">
          {explanation.summary ? (
            <p className="text-sm sm:text-[15px] leading-relaxed text-[var(--fg-primary)] m-0 max-w-[72ch]">
              {explanation.summary}
            </p>
          ) : (
            <p className="text-xs text-[var(--fg-muted)] italic m-0">
              Summary omitted because a generated quotation could not be verified word-for-word against the sources.
            </p>
          )}

          {explanation.reasons.length > 0 && (
            <ol className="space-y-2.5 list-none p-0 m-0 pt-1">
              {explanation.reasons.map((reason, idx) => (
                <li
                  key={`${idx}-${reason.evidence_ids.join(",")}`}
                  className="flex items-start gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] p-3.5"
                >
                  <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--bg-subtle)] font-mono-num text-xs font-semibold text-[var(--fg-secondary)] mt-0.5">
                    {idx + 1}
                  </span>
                  <div className="space-y-2 min-w-0 flex-1">
                    <p className="text-sm text-[var(--fg-primary)] leading-relaxed m-0">
                      {reason.text}
                    </p>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] text-[var(--fg-muted)]">Sources:</span>
                      {reason.evidence_ids.map((eid) => {
                        const ev = evidenceMap.get(eid);
                        const isActive = activeEvidenceId === eid;
                        return (
                          <button
                            key={eid}
                            type="button"
                            onClick={() => onSelectEvidence(eid)}
                            title={ev ? ev.detail : `Evidence ${eid}`}
                            className={cn(
                              "inline-flex items-center gap-1 px-2 py-0.5 rounded font-mono-num text-xs font-medium border transition-colors cursor-pointer",
                              isActive
                                ? "bg-[var(--accent)] text-white border-[var(--accent)]"
                                : "bg-[var(--accent-soft)] text-[var(--accent)] border-[var(--accent-border)] hover:opacity-85",
                            )}
                          >
                            [{eid}]
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  );
}
