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
import { ArrowRight, Check, ChevronDown, Loader2, X } from "lucide-react";
import { ApiClientError, createAnalysis } from "../lib/api";
import type { InputKind } from "../lib/contracts";
import { cleanDomain } from "../lib/evidence";
import { detectInputKind } from "../lib/format";
import { EXPLANATION_LANGUAGE_OPTIONS } from "../lib/labels";
import { buttonClass } from "../lib/ui";
import { cn } from "../lib/utils";
import { Favicon } from "./ui/Favicon";

export interface PrefillValue {
  readonly value: string;
  readonly kind?: InputKind;
  readonly nonce: number;
}

export interface AnalysisInputFormProps {
  readonly prefill?: PrefillValue | null;
}

const MODE_OPTIONS: readonly { readonly id: "auto" | InputKind; readonly label: string }[] = [
  { id: "auto", label: "Detect automatically" },
  { id: "url", label: "Link" },
  { id: "text", label: "Text" },
];

const MENU_ITEM =
  "w-full flex items-center justify-between gap-2 h-8 px-2.5 rounded-md text-[13px] text-left transition-colors cursor-pointer";

export function AnalysisInputForm({ prefill }: Readonly<AnalysisInputFormProps>) {
  const navigate = useNavigate();
  const inputId = useId();
  const customLangId = useId();
  const errorId = useId();
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const [value, setValue] = useState("");
  const [kindOverride, setKindOverride] = useState<"auto" | InputKind>("auto");
  const [langChoice, setLangChoice] = useState("");
  const [customLang, setCustomLang] = useState("");
  const [force, setForce] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modeOpen, setModeOpen] = useState(false);

  useEffect(() => {
    if (!prefill) return;
    setValue(prefill.value);
    setKindOverride("auto");
    setError(null);
    requestAnimationFrame(() => textareaRef.current?.focus());
  }, [prefill]);

  // Grow with the content between ~3 and ~9 lines.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.max(72, Math.min(el.scrollHeight, 232))}px`;
  }, [value]);

  const trimmed = value.trim();
  const effectiveKind: InputKind = kindOverride === "auto" ? detectInputKind(trimmed) : kindOverride;
  const wordCount = trimmed ? trimmed.split(/\s+/).length : 0;
  const urlDomain = effectiveKind === "url" && trimmed ? cleanDomain(trimmed) : "";
  const resolvedLanguage = langChoice === "__custom__" ? customLang.trim().toLowerCase() : langChoice;
  const singleLineUrl = effectiveKind === "url" && !trimmed.includes("\n");

  async function submitCurrentInput() {
    setError(null);
    if (!trimmed) {
      setError("Paste a link or some text first.");
      textareaRef.current?.focus();
      return;
    }
    if (effectiveKind === "url" && !/^https?:\/\/\S+$/i.test(trimmed)) {
      setError("That is not a full http(s) link. Switch to Text to analyse it as text.");
      return;
    }
    if (langChoice === "__custom__" && resolvedLanguage && !/^[a-z]{2,3}$/i.test(resolvedLanguage)) {
      setError("Use a 2- or 3-letter language code, like fi or cs.");
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
      setError(err instanceof ApiClientError ? err.message : "Could not reach the analysis service.");
      setSubmitting(false);
    }
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void submitCurrentInput();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== "Enter" || submitting) return;
    // ⌘/Ctrl+Enter always sends; plain Enter sends a single-line link.
    if (e.metaKey || e.ctrlKey || (!e.shiftKey && singleLineUrl && trimmed.length > 0)) {
      e.preventDefault();
      void submitCurrentInput();
    }
  }

  const kindLabel = !trimmed
    ? kindOverride === "auto"
      ? "Link or text"
      : kindOverride === "url"
        ? "Link"
        : "Text"
    : effectiveKind === "url"
      ? urlDomain || "Link"
      : `Text · ${wordCount} ${wordCount === 1 ? "word" : "words"}`;

  return (
    <form onSubmit={handleSubmit} noValidate className="w-full space-y-2">
      <div data-spotlight className="omnibox-shell rounded-2xl">
        <label htmlFor={inputId} className="sr-only">
          Article link or text to analyse
        </label>
        <div className="relative">
          <textarea
            ref={textareaRef}
            id={inputId}
            rows={3}
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              if (error) setError(null);
            }}
            onKeyDown={handleKeyDown}
            disabled={submitting}
            aria-invalid={error ? "true" : "false"}
            aria-describedby={error ? errorId : undefined}
            placeholder="Paste an article link or any text…"
            className={cn(
              "block w-full resize-none bg-transparent border-0 outline-none focus-visible:outline-none px-4 pt-4 pb-2 pr-11 text-[var(--fg-primary)] placeholder:text-[var(--fg-muted)] leading-relaxed",
              singleLineUrl && trimmed ? "font-mono-num text-[13px]" : "text-[15px]",
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
              aria-label="Clear"
              className={buttonClass("ghost", "icon", "absolute top-2.5 right-2.5 h-7 w-7")}
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          )}
        </div>

        <div className="flex items-center justify-between gap-2 px-2.5 pb-2.5">
          <div className="flex items-center gap-0.5 min-w-0">
            <Popover.Root open={modeOpen} onOpenChange={setModeOpen}>
              <Popover.Trigger asChild>
                <button type="button" className={buttonClass("ghost", "sm", "max-w-[220px]")}>
                  {effectiveKind === "url" && urlDomain && <Favicon domain={urlDomain} size={14} />}
                  <span className="truncate">{kindLabel}</span>
                  <ChevronDown className="h-3 w-3 opacity-60 shrink-0" aria-hidden="true" />
                </button>
              </Popover.Trigger>
              <Popover.Portal>
                <Popover.Content
                  align="start"
                  sideOffset={6}
                  className="z-50 glass-popover rounded-lg p-1 w-52 outline-none"
                >
                  {MODE_OPTIONS.map((opt) => {
                    const selected = kindOverride === opt.id;
                    return (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => {
                          setKindOverride(opt.id);
                          setModeOpen(false);
                        }}
                        className={cn(
                          MENU_ITEM,
                          selected
                            ? "bg-[var(--bg-hover)] text-[var(--fg-primary)]"
                            : "text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]",
                        )}
                      >
                        {opt.label}
                        {selected && <Check className="h-3.5 w-3.5" aria-hidden="true" />}
                      </button>
                    );
                  })}
                </Popover.Content>
              </Popover.Portal>
            </Popover.Root>

            <Popover.Root>
              <Popover.Trigger asChild>
                <button type="button" className={buttonClass("ghost", "sm")}>
                  <span>
                    Summary in{" "}
                    <span className="font-mono-num uppercase text-[var(--fg-primary)]">
                      {resolvedLanguage || "en"}
                    </span>
                  </span>
                  {force && (
                    <span
                      className="h-1.5 w-1.5 rounded-full bg-[var(--caution)]"
                      title="Fresh run: cache bypassed"
                    />
                  )}
                  <ChevronDown className="h-3 w-3 opacity-60" aria-hidden="true" />
                </button>
              </Popover.Trigger>
              <Popover.Portal>
                <Popover.Content
                  align="start"
                  sideOffset={6}
                  className="z-50 glass-popover rounded-lg p-3 w-64 space-y-3 outline-none"
                >
                  <label className="block space-y-1.5">
                    <span className="block text-xs font-medium text-[var(--fg-secondary)]">
                      Summary language
                    </span>
                    <select
                      value={langChoice}
                      onChange={(e) => setLangChoice(e.target.value)}
                      className="w-full h-8 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-surface)] px-2 text-[13px] text-[var(--fg-primary)] outline-none focus:border-[var(--accent)]"
                    >
                      {EXPLANATION_LANGUAGE_OPTIONS.map((opt) => (
                        <option key={opt.code || "default"} value={opt.code}>
                          {opt.label}
                        </option>
                      ))}
                      <option value="__custom__">Other code…</option>
                    </select>
                  </label>

                  {langChoice === "__custom__" && (
                    <div>
                      <label htmlFor={customLangId} className="sr-only">
                        Language code
                      </label>
                      <input
                        id={customLangId}
                        type="text"
                        maxLength={3}
                        placeholder="fi, cs, sv…"
                        value={customLang}
                        onChange={(e) => setCustomLang(e.target.value)}
                        className="w-full h-8 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-surface)] px-2 text-[13px] font-mono-num text-[var(--fg-primary)] outline-none focus:border-[var(--accent)]"
                      />
                    </div>
                  )}

                  <label className="flex items-center justify-between gap-3 pt-3 border-t border-[var(--border-subtle)] cursor-pointer">
                    <span className="text-[13px] text-[var(--fg-primary)]">Skip the cache</span>
                    <input
                      type="checkbox"
                      checked={force}
                      onChange={(e) => setForce(e.target.checked)}
                      className="h-4 w-4 accent-[var(--accent)] cursor-pointer"
                    />
                  </label>
                </Popover.Content>
              </Popover.Portal>
            </Popover.Root>
          </div>

          <div className="flex items-center gap-2.5 shrink-0">
            <kbd className="hidden sm:inline text-[11px] font-mono-num text-[var(--fg-muted)]">
              {singleLineUrl ? "↵" : "⌘↵"}
            </kbd>
            <button
              type="submit"
              disabled={submitting || !trimmed}
              className={buttonClass("primary", "md", "px-3.5")}
            >
              {submitting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              ) : (
                <>
                  Analyze
                  <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      <AnimatePresence>
        {error && (
          <motion.p
            id={errorId}
            role="alert"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="px-1 text-[13px] text-[var(--danger)]"
          >
            {error}
          </motion.p>
        )}
      </AnimatePresence>
    </form>
  );
}
