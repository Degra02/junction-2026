import { useEffect, useId, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { AlertCircle, ArrowRight, Globe, Link2, FileText, RotateCw } from "lucide-react";
import { ApiClientError, createAnalysis } from "../lib/api";
import type { InputKind } from "../lib/contracts";
import { detectInputKind } from "../lib/format";
import { EXPLANATION_LANGUAGE_OPTIONS } from "../lib/labels";
import { cn } from "../lib/utils";

export interface PrefillValue {
  readonly value: string;
  readonly kind?: InputKind;
  readonly nonce: number;
}

export interface AnalysisInputFormProps {
  readonly prefill?: PrefillValue | null;
}

export function AnalysisInputForm({ prefill }: Readonly<AnalysisInputFormProps>) {
  const navigate = useNavigate();
  const inputId = useId();
  const langSelectId = useId();
  const customLangId = useId();
  const errorId = useId();

  const [value, setValue] = useState<string>("");
  const [kindOverride, setKindOverride] = useState<"auto" | InputKind>("auto");
  const [langChoice, setLangChoice] = useState<string>("");
  const [customLang, setCustomLang] = useState<string>("");
  const [force, setForce] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!prefill) return;
    setValue(prefill.value);
    setKindOverride(prefill.kind ?? "auto");
    setError(null);
  }, [prefill]);

  const trimmed = value.trim();
  const effectiveKind: InputKind =
    kindOverride === "auto" ? detectInputKind(trimmed) : kindOverride;

  const resolvedLanguage =
    langChoice === "__custom__" ? customLang.trim().toLowerCase() : langChoice;

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);

    if (!trimmed) {
      setError("Paste an article text, social post, or public http(s) article URL to analyse.");
      return;
    }

    if (resolvedLanguage && !/^[a-z]{2,3}(-[a-z0-9]+)?$/i.test(resolvedLanguage)) {
      setError("Explanation language must be a 2–3 letter ISO language code (such as de, fr, it, fi).");
      return;
    }

    setSubmitting(true);
    try {
      const created = await createAnalysis(
        {
          kind: effectiveKind,
          value: trimmed,
          explanation_language: resolvedLanguage || null,
        },
        { force },
      );
      navigate(`/analyses/${created.id}`);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Could not start the analysis. Check that the API is reachable.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-describedby={error ? errorId : undefined}
      className="rounded-xl border border-[var(--border-strong)] bg-[var(--bg-surface)] p-4 sm:p-5 space-y-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label htmlFor={inputId} className="text-sm font-semibold text-[var(--fg-primary)]">
          Paste content or an article URL
        </label>

        <div className="inline-flex items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-0.5 text-xs">
          {(
            [
              { key: "auto", label: `Auto (${effectiveKind === "url" ? "URL" : "Text"})` },
              { key: "text", label: "Text" },
              { key: "url", label: "URL" },
            ] as const
          ).map((opt) => (
            <button
              key={opt.key}
              type="button"
              onClick={() => setKindOverride(opt.key)}
              className={cn(
                "px-2.5 py-1 rounded-md font-medium transition-colors cursor-pointer",
                kindOverride === opt.key
                  ? "bg-[var(--bg-surface)] text-[var(--fg-primary)] shadow-2xs"
                  : "text-[var(--fg-muted)] hover:text-[var(--fg-primary)]",
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="relative">
        <textarea
          id={inputId}
          name="content"
          rows={effectiveKind === "url" ? 3 : 6}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            if (error) setError(null);
          }}
          placeholder="Paste a news article, a social-media claim in any language, or an https:// link to an article…"
          className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-canvas)] px-3.5 py-3 text-sm leading-relaxed text-[var(--fg-primary)] placeholder:text-[var(--fg-muted)] focus:border-[var(--accent)] focus:outline-2 focus:outline-[var(--accent)]/25 resize-y transition-colors"
        />
        <div className="mt-1.5 flex items-center justify-between text-xs text-[var(--fg-muted)]">
          <span className="inline-flex items-center gap-1.5">
            {effectiveKind === "url" ? (
              <>
                <Link2 className="h-3.5 w-3.5 text-[var(--accent)]" aria-hidden="true" />
                <span>Article URL — pipeline will fetch &amp; extract full page text and tracking IDs</span>
              </>
            ) : (
              <>
                <FileText className="h-3.5 w-3.5 text-[var(--fg-muted)]" aria-hidden="true" />
                <span>Pasted text — language detected automatically across 75 languages</span>
              </>
            )}
          </span>
          <span className="font-mono-num shrink-0">{Array.from(trimmed).length.toLocaleString()} chars</span>
        </div>
      </div>

      <div className="pt-2 border-t border-[var(--border-subtle)] flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label
              htmlFor={langSelectId}
              className="flex items-center gap-1.5 text-xs font-medium text-[var(--fg-secondary)] mb-1"
            >
              <Globe className="h-3.5 w-3.5 text-[var(--fg-muted)]" aria-hidden="true" />
              Explanation language
            </label>
            <select
              id={langSelectId}
              value={langChoice}
              onChange={(e) => setLangChoice(e.target.value)}
              className="h-9 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-canvas)] px-2.5 text-xs font-medium text-[var(--fg-primary)] focus:border-[var(--accent)] focus:outline-none"
            >
              {EXPLANATION_LANGUAGE_OPTIONS.map((opt) => (
                <option key={opt.code || "en"} value={opt.code}>
                  {opt.label}
                </option>
              ))}
              <option value="__custom__">Other ISO code…</option>
            </select>
          </div>

          {langChoice === "__custom__" && (
            <div>
              <label
                htmlFor={customLangId}
                className="block text-xs font-medium text-[var(--fg-secondary)] mb-1"
              >
                ISO 639-1 code
              </label>
              <input
                id={customLangId}
                type="text"
                maxLength={8}
                placeholder="e.g. fi"
                value={customLang}
                onChange={(e) => setCustomLang(e.target.value)}
                className="h-9 w-24 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-canvas)] px-2.5 text-xs font-mono-num text-[var(--fg-primary)] focus:border-[var(--accent)] focus:outline-none"
              />
            </div>
          )}

          <label className="inline-flex items-center gap-2 h-9 px-2.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-subtle)] text-xs text-[var(--fg-secondary)] cursor-pointer select-none">
            <input
              type="checkbox"
              checked={force}
              onChange={(e) => setForce(e.target.checked)}
              className="accent-[var(--accent)] rounded"
            />
            <RotateCw className="h-3 w-3 text-[var(--fg-muted)]" aria-hidden="true" />
            <span>Bypass cache</span>
          </label>
        </div>

        <button
          type="submit"
          disabled={submitting || trimmed.length === 0}
          className={cn(
            "inline-flex items-center justify-center gap-2 h-10 px-5 rounded-lg text-sm font-semibold text-white bg-[var(--accent)] hover:bg-[var(--accent-hover)] active:translate-y-[1px] transition-all cursor-pointer shrink-0",
            "disabled:opacity-50 disabled:pointer-events-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
          )}
        >
          <span>{submitting ? "Starting analysis…" : "Analyse coverage & signals"}</span>
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      {error && (
        <div
          id={errorId}
          role="alert"
          className="flex items-start gap-2.5 rounded-lg border border-[var(--danger-border)] bg-[var(--danger-soft)] px-3.5 py-2.5 text-xs text-[var(--danger)]"
        >
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}
    </form>
  );
}
