import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { useNavigate } from "react-router-dom";
import * as Popover from "@radix-ui/react-popover";
import { AnimatePresence, motion } from "motion/react";
import {
  AlertCircle,
  ArrowUp,
  Check,
  ChevronDown,
  FileText,
  Globe,
  Link2,
  Loader2,
  RotateCw,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";
import { ApiClientError, createAnalysis } from "../lib/api";
import type { InputKind } from "../lib/contracts";
import { cleanDomain } from "../lib/evidence";
import { detectInputKind } from "../lib/format";
import { EXPLANATION_LANGUAGE_OPTIONS } from "../lib/labels";
import { SNAPPY_SPRING } from "../lib/motion";
import { cn } from "../lib/utils";

export interface PrefillValue {
  readonly value: string;
  readonly kind?: InputKind;
  readonly nonce: number;
}

export interface AnalysisInputFormProps {
  readonly prefill?: PrefillValue | null;
  readonly compact?: boolean;
}

const MODE_OPTIONS: readonly {
  readonly id: "auto" | InputKind;
  readonly label: string;
  readonly desc: string;
}[] = [
  { id: "auto", label: "Automatic", desc: "Detect URL vs. pasted text automatically" },
  { id: "url", label: "Article URL", desc: "Fetch webpage, metadata, and tracking IDs" },
  { id: "text", label: "Plain text", desc: "Analyse pasted paragraphs or social post directly" },
];

export function AnalysisInputForm({ prefill, compact = false }: Readonly<AnalysisInputFormProps>) {
  const navigate = useNavigate();
  const inputId = useId();
  const customLangId = useId();
  const errorId = useId();
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const [value, setValue] = useState<string>("");
  const [kindOverride, setKindOverride] = useState<"auto" | InputKind>("auto");
  const [langChoice, setLangChoice] = useState<string>("");
  const [customLang, setCustomLang] = useState<string>("");
  const [force, setForce] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [modePopoverOpen, setModePopoverOpen] = useState<boolean>(false);

  useEffect(() => {
    if (!prefill) return;
    setValue(prefill.value);
    setKindOverride("auto");
    setError(null);
    requestAnimationFrame(() => {
      textareaRef.current?.focus();
    });
  }, [prefill]);

  // Auto-resize textarea cleanly between 2 and 9 lines
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const minH = compact ? 56 : 76;
    const maxH = 240;
    el.style.height = `${Math.max(minH, Math.min(el.scrollHeight, maxH))}px`;
  }, [value, compact]);

  const trimmed = value.trim();
  const detectedKind: InputKind = detectInputKind(trimmed);
  const effectiveKind: InputKind = kindOverride === "auto" ? detectedKind : kindOverride;

  const wordCount = trimmed ? trimmed.split(/\s+/).length : 0;
  const urlDomain = effectiveKind === "url" && trimmed ? cleanDomain(trimmed) : "";

  const resolvedLanguage =
    langChoice === "__custom__" ? customLang.trim().toLowerCase() : langChoice;

  async function submitCurrentInput() {
    setError(null);
    if (!trimmed) {
      setError("Paste an article link, claim, or paragraph to investigate.");
      textareaRef.current?.focus();
      return;
    }

    if (effectiveKind === "url" && !/^https?:\/\/\S+$/i.test(trimmed)) {
      setError("Enter a complete http:// or https:// URL, or switch input mode to Automatic.");
      return;
    }

    if (langChoice === "__custom__" && resolvedLanguage && !/^[a-z]{2,3}$/i.test(resolvedLanguage)) {
      setError("Explanation language must be a 2- or 3-letter ISO code (e.g. en, de, it).");
      return;
    }

    setSubmitting(true);
    try {
      const created = await createAnalysis(
        {
          kind: effectiveKind,
          value: trimmed,
          explanation_language: resolvedLanguage ? resolvedLanguage : null,
        },
        { force },
      );
      navigate(`/analyses/${created.id}`);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Could not reach the analysis API. Make sure the backend or proxy is running.");
      }
      setSubmitting(false);
    }
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void submitCurrentInput();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Submit on Enter for single-line URLs, or Cmd/Ctrl+Enter for any multi-line text
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      if (!submitting) void submitCurrentInput();
      return;
    }
    if (
      e.key === "Enter" &&
      !e.shiftKey &&
      effectiveKind === "url" &&
      !trimmed.includes("\n") &&
      trimmed.length > 0
    ) {
      e.preventDefault();
      if (!submitting) void submitCurrentInput();
    }
  }

  const activeLangBadge = resolvedLanguage ? resolvedLanguage.toUpperCase() : "EN";

  return (
    <form onSubmit={handleSubmit} noValidate className="w-full space-y-2.5">
      <div className="omnibox-shell rounded-3xl p-3 sm:p-4 flex flex-col gap-3">
        <div className="relative flex items-start gap-2">
          <label htmlFor={inputId} className="sr-only">
            Paste article URL or text to analyse
          </label>
          <textarea
            ref={textareaRef}
            id={inputId}
            rows={compact ? 2 : 3}
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              if (error) setError(null);
            }}
            onKeyDown={handleKeyDown}
            disabled={submitting}
            aria-invalid={error ? "true" : "false"}
            aria-describedby={error ? errorId : undefined}
            placeholder="Paste an article URL, social post, or claim in any language…"
            className={cn(
              "w-full resize-none bg-transparent border-0 outline-none px-1.5 py-1 text-[var(--fg-primary)] placeholder:text-[var(--fg-muted)]/80 leading-relaxed",
              effectiveKind === "url" && trimmed
                ? "font-mono-num text-xs sm:text-sm"
                : "text-sm sm:text-[15px]",
            )}
          />

          {value.length > 0 && !submitting && (
            <button
              type="button"
              onClick={() => {
                setValue("");
                setError(null);
                textareaRef.current?.focus();
              }}
              aria-label="Clear input"
              className="mt-1 h-7 w-7 rounded-full inline-flex items-center justify-center text-[var(--fg-muted)] hover:text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)] transition-colors shrink-0 cursor-pointer"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          )}
        </div>

        {/* Bottom Floating Control Strip inside Omnibox */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-[var(--border-subtle)]/70">
          <div className="flex flex-wrap items-center gap-1.5">
            {/* Input Mode Pill (Auto / URL / Text) */}
            <Popover.Root open={modePopoverOpen} onOpenChange={setModePopoverOpen}>
              <Popover.Trigger asChild>
                <button
                  type="button"
                  className={cn(
                    "inline-flex items-center gap-1.5 h-8 px-2.5 rounded-full text-xs font-medium border transition-colors cursor-pointer",
                    trimmed
                      ? "bg-[var(--accent-soft)] border-[var(--accent-border)] text-[var(--accent)]"
                      : "bg-[var(--bg-subtle)]/70 border-[var(--border-subtle)] text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]",
                  )}
                >
                  {!trimmed && kindOverride === "auto" ? (
                    <>
                      <Sparkles className="h-3.5 w-3.5 text-[var(--accent)]" aria-hidden="true" />
                      <span>Automatic</span>
                    </>
                  ) : effectiveKind === "url" ? (
                    <>
                      <Link2 className="h-3.5 w-3.5" aria-hidden="true" />
                      <span className="truncate max-w-[170px]">
                        {kindOverride === "auto" ? "Auto: URL" : "URL"}
                        {urlDomain ? ` · ${urlDomain}` : ""}
                      </span>
                    </>
                  ) : (
                    <>
                      <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                      <span>
                        {kindOverride === "auto" ? "Auto: Text" : "Text"}
                        {wordCount > 0 ? ` · ${wordCount}w` : ""}
                      </span>
                    </>
                  )}
                  <ChevronDown className="h-3 w-3 opacity-70" aria-hidden="true" />
                </button>
              </Popover.Trigger>
              <Popover.Portal>
                <Popover.Content
                  align="start"
                  sideOffset={8}
                  className="z-50 glass-popover rounded-2xl p-1.5 w-64 space-y-0.5 outline-none"
                >
                  {MODE_OPTIONS.map((opt) => {
                    const selected = kindOverride === opt.id;
                    return (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => {
                          setKindOverride(opt.id);
                          setModePopoverOpen(false);
                        }}
                        className={cn(
                          "w-full text-left px-3 py-2 rounded-xl flex items-start justify-between gap-2 transition-colors cursor-pointer",
                          selected
                            ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                            : "hover:bg-[var(--bg-subtle)]/80 text-[var(--fg-primary)]",
                        )}
                      >
                        <div>
                          <div className="text-xs font-semibold">{opt.label}</div>
                          <div className="text-[11px] text-[var(--fg-muted)] leading-snug">
                            {opt.desc}
                          </div>
                        </div>
                        {selected && <Check className="h-3.5 w-3.5 shrink-0 mt-0.5" aria-hidden="true" />}
                      </button>
                    );
                  })}
                </Popover.Content>
              </Popover.Portal>
            </Popover.Root>

            {/* Options Popover (Explanation Language + Bypass Cache) */}
            <Popover.Root>
              <Popover.Trigger asChild>
                <button
                  type="button"
                  className={cn(
                    "inline-flex items-center gap-1.5 h-8 px-2.5 rounded-full text-xs font-medium border transition-colors cursor-pointer",
                    resolvedLanguage || force
                      ? "bg-[var(--bg-surface)] border-[var(--border-strong)] text-[var(--fg-primary)]"
                      : "bg-[var(--bg-subtle)]/70 border-[var(--border-subtle)] text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]",
                  )}
                >
                  <Globe className="h-3.5 w-3.5 text-[var(--fg-muted)]" aria-hidden="true" />
                  <span className="font-mono-num">{activeLangBadge}</span>
                  {force && (
                    <span className="h-1.5 w-1.5 rounded-full bg-[var(--caution)]" title="Fresh run enabled" />
                  )}
                  <SlidersHorizontal className="h-3 w-3 opacity-70" aria-hidden="true" />
                </button>
              </Popover.Trigger>
              <Popover.Portal>
                <Popover.Content
                  align="start"
                  sideOffset={8}
                  className="z-50 glass-popover rounded-2xl p-3.5 w-72 space-y-3.5 outline-none"
                >
                  <div className="space-y-1.5">
                    <div className="text-xs font-semibold text-[var(--fg-primary)]">
                      Explanation language
                    </div>
                    <p className="text-[11px] text-[var(--fg-muted)] m-0 leading-snug">
                      Content is analysed in its own language; choose the language for the written summary.
                    </p>
                    <select
                      value={langChoice}
                      onChange={(e) => setLangChoice(e.target.value)}
                      className="w-full h-8 rounded-xl border border-[var(--border-strong)] bg-[var(--bg-surface)] px-2.5 text-xs text-[var(--fg-primary)] outline-none focus:border-[var(--accent)]"
                    >
                      {EXPLANATION_LANGUAGE_OPTIONS.map((opt) => (
                        <option key={opt.code || "default"} value={opt.code}>
                          {opt.label}
                        </option>
                      ))}
                      <option value="__custom__">Other ISO-639 code…</option>
                    </select>

                    {langChoice === "__custom__" && (
                      <div className="pt-1">
                        <label htmlFor={customLangId} className="sr-only">
                          Custom ISO language code
                        </label>
                        <input
                          id={customLangId}
                          type="text"
                          maxLength={3}
                          placeholder="e.g. fi, cs, sv"
                          value={customLang}
                          onChange={(e) => setCustomLang(e.target.value)}
                          className="w-full h-8 rounded-xl border border-[var(--border-strong)] bg-[var(--bg-surface)] px-2.5 text-xs font-mono-num text-[var(--fg-primary)]"
                        />
                      </div>
                    )}
                  </div>

                  <div className="pt-2.5 border-t border-[var(--border-subtle)] flex items-center justify-between gap-3">
                    <div className="space-y-0.5">
                      <div className="text-xs font-semibold text-[var(--fg-primary)] flex items-center gap-1.5">
                        <RotateCw className="h-3 w-3 text-[var(--fg-muted)]" aria-hidden="true" />
                        <span>Bypass cache</span>
                      </div>
                      <p className="text-[11px] text-[var(--fg-muted)] m-0">
                        Re-scrape live sources instead of reusing a cached run.
                      </p>
                    </div>
                    <input
                      type="checkbox"
                      checked={force}
                      onChange={(e) => setForce(e.target.checked)}
                      className="h-4 w-4 accent-[var(--accent)] rounded cursor-pointer shrink-0"
                    />
                  </div>
                </Popover.Content>
              </Popover.Portal>
            </Popover.Root>
          </div>

          {/* Right Side: Keyboard Hint + Send Key */}
          <div className="flex items-center gap-2.5 ml-auto">
            <span className="hidden sm:inline-block text-[11px] font-mono-num text-[var(--fg-muted)] select-none">
              {effectiveKind === "url" && !trimmed.includes("\n") ? "↵ to send" : "⌘↵ to send"}
            </span>

            <motion.button
              whileTap={{ scale: 0.94 }}
              transition={SNAPPY_SPRING}
              type="submit"
              disabled={submitting || !trimmed}
              aria-label="Run propaganda and coordination analysis"
              className={cn(
                "inline-flex items-center justify-center gap-1.5 h-9 px-4 rounded-full text-xs font-semibold transition-all cursor-pointer",
                trimmed && !submitting
                  ? "bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white shadow-sm"
                  : "bg-[var(--bg-subtle)] text-[var(--fg-muted)] border border-[var(--border-subtle)] cursor-not-allowed",
              )}
            >
              {submitting ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                  <span>Starting…</span>
                </>
              ) : (
                <>
                  <span>Investigate</span>
                  <ArrowUp className="h-3.5 w-3.5" aria-hidden="true" />
                </>
              )}
            </motion.button>
          </div>
        </div>
      </div>

      {/* Inline Floating Validation Error */}
      <AnimatePresence>
        {error && (
          <motion.div
            id={errorId}
            role="alert"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            className="rounded-2xl border border-[var(--danger-border)] bg-[var(--danger-soft)] px-4 py-2.5 flex items-center gap-2 text-xs text-[var(--danger)]"
          >
            <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </motion.div>
        )}
      </AnimatePresence>
    </form>
  );
}
