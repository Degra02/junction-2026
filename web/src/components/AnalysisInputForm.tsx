import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import * as Popover from "@radix-ui/react-popover";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, Check, ChevronDown, Loader2, X } from "lucide-react";
import { createAnalysis, describeError } from "../lib/api";
import type { InputKind } from "../lib/contracts";
import { cleanDomain } from "../lib/evidence";
import { detectInputKind, withScheme } from "../lib/format";
import { EXPLANATION_LANGUAGE_OPTIONS } from "../lib/labels";
import { buttonClass } from "../lib/ui";
import { cn } from "../lib/utils";
import { Favicon } from "./ui/Favicon";

export interface PrefillValue {
  readonly value: string;
  readonly kind?: InputKind;
  readonly lang?: string;
  readonly autoSubmit?: boolean;
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

/** The API's default `MAX_INPUT_CHARS`; longer text is refused there. */
const MAX_TEXT_CHARS = 50_000;
/** Below this many words the analysis rarely finds other reports to compare. */
const SHORT_TEXT_WORDS = 12;

const IS_MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

export function AnalysisInputForm({ prefill }: Readonly<AnalysisInputFormProps>) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const inputId = useId();
  const customLangId = useId();
  const errorId = useId();
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const autoSubmittedNonceRef = useRef<number | null>(null);

  const [value, setValue] = useState("");
  const [kindOverride, setKindOverride] = useState<"auto" | InputKind>(() => {
    const mode = searchParams.get("mode");
    return mode === "text" || mode === "url" ? mode : "auto";
  });
  const [langChoice, setLangChoice] = useState("");
  const [customLang, setCustomLang] = useState("");
  const [force, setForce] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modeOpen, setModeOpen] = useState(false);
  const [focused, setFocused] = useState(false);
  // Text the user had before an example or Clear replaced it, for Undo.
  const [replaced, setReplaced] = useState<{ text: string; by: "example" | "clear" } | null>(null);
  const valueRef = useRef(value);
  valueRef.current = value;

  useEffect(() => {
    if (!prefill) return;
    const nextValue = prefill.value;
    const nextKind: "auto" | InputKind = prefill.kind ?? "auto";
    const nextLang = (prefill.lang ?? "").trim().toLowerCase();
    const knownCodes = new Set(EXPLANATION_LANGUAGE_OPTIONS.map((o) => o.code));

    const previous = valueRef.current;
    setReplaced(previous.trim() && previous !== nextValue ? { text: previous, by: "example" } : null);
    setValue(nextValue);
    setKindOverride(nextKind);
    if (nextLang) {
      if (knownCodes.has(nextLang)) {
        setLangChoice(nextLang);
        setCustomLang("");
      } else {
        setLangChoice("__custom__");
        setCustomLang(nextLang);
      }
    }
    setError(null);

    if (prefill.autoSubmit && autoSubmittedNonceRef.current !== prefill.nonce) {
      autoSubmittedNonceRef.current = prefill.nonce;
      const clean = nextValue.trim();
      const resolvedKind: InputKind = nextKind === "auto" ? detectInputKind(clean) : nextKind;
      if (!clean) return;
      const submitted = resolvedKind === "url" ? withScheme(clean) : clean;
      if (resolvedKind === "url" && !/^https?:\/\/\S+$/i.test(submitted)) {
        setError("That is not a link. Switch to Text to analyse it as text.");
        return;
      }
      setSubmitting(true);
      createAnalysis({ kind: resolvedKind, value: submitted, explanation_language: nextLang || null })
        .then((created) => {
          navigate(`/analyses/${created.id}`, { replace: true });
        })
        .catch((err: unknown) => {
          setError(describeError(err));
          setSubmitting(false);
        });
      return;
    }

    requestAnimationFrame(() => textareaRef.current?.focus());
  }, [prefill, navigate]);

  // Arriving with ?mode=text (e.g. "Paste the text instead" after a page could not be read).
  useEffect(() => {
    if (searchParams.get("mode")) textareaRef.current?.focus();
  }, [searchParams]);

  // "/" focuses the composer from anywhere on the page, as on GitHub or YouTube.
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
      e.preventDefault();
      textareaRef.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

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
  const charCount = Array.from(trimmed).length;
  const urlDomain = effectiveKind === "url" && trimmed ? cleanDomain(trimmed) : "";
  const resolvedLanguage = langChoice === "__custom__" ? customLang.trim().toLowerCase() : langChoice;
  const singleLineUrl = effectiveKind === "url" && !trimmed.includes("\n");
  const tooLong = effectiveKind === "text" && charCount > MAX_TEXT_CHARS;
  const shortText = effectiveKind === "text" && wordCount > 0 && wordCount < SHORT_TEXT_WORDS;

  async function submitCurrentInput() {
    setError(null);
    if (!trimmed) {
      setError("Paste a link or some text first.");
      textareaRef.current?.focus();
      return;
    }
    const submitted = effectiveKind === "url" ? withScheme(trimmed) : trimmed;
    if (effectiveKind === "url" && !/^https?:\/\/\S+$/i.test(submitted)) {
      setError("That is not a link. Switch to Text to analyse it as text.");
      return;
    }
    if (tooLong) {
      setError(`The text has ${charCount.toLocaleString("en")} characters; the limit is ${MAX_TEXT_CHARS.toLocaleString("en")}. Shorten it, or paste the article's link instead.`);
      return;
    }
    if (langChoice === "__custom__" && resolvedLanguage && !/^[a-z]{2,3}$/i.test(resolvedLanguage)) {
      setError("Use a 2- or 3-letter language code, like fi or cs.");
      return;
    }

    setSubmitting(true);
    try {
      const created = await createAnalysis(
        { kind: effectiveKind, value: submitted, explanation_language: resolvedLanguage || null },
        { force },
      );
      navigate(`/analyses/${created.id}`);
    } catch (err: unknown) {
      setError(describeError(err));
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
      : charCount > MAX_TEXT_CHARS * 0.8
        ? `Text · ${charCount.toLocaleString("en")} / ${MAX_TEXT_CHARS.toLocaleString("en")} characters`
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
              setReplaced(null);
              if (error) setError(null);
            }}
            onKeyDown={handleKeyDown}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            disabled={submitting}
            aria-invalid={error ? "true" : "false"}
            aria-describedby={error ? errorId : undefined}
            aria-keyshortcuts="/"
            placeholder="Paste an article link or any text…"
            className={cn(
              "block w-full resize-none bg-transparent border-0 outline-none focus-visible:outline-none px-4 pt-4 pb-2 pr-11 text-[var(--fg-primary)] placeholder:text-[var(--fg-muted)] leading-relaxed",
              singleLineUrl && trimmed ? "font-mono-num text-[13px]" : "text-[15px]",
            )}
          />
          {value.length > 0 && !submitting ? (
            <button
              type="button"
              onClick={() => {
                setReplaced({ text: value, by: "clear" });
                setValue("");
                setError(null);
                textareaRef.current?.focus();
              }}
              aria-label="Clear"
              title="Clear"
              className={buttonClass("ghost", "icon", "absolute top-2.5 right-2.5 h-7 w-7")}
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          ) : (
            !focused && (
              <kbd
                title="Press / to type here"
                className="hidden sm:inline-flex absolute top-3.5 right-3.5 h-5 min-w-5 items-center justify-center rounded border border-[var(--border-subtle)] px-1 font-mono-num text-[11px] text-[var(--fg-muted)]"
              >
                /
              </kbd>
            )
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
              {singleLineUrl ? "↵" : IS_MAC ? "⌘↵" : "Ctrl ↵"}
            </kbd>
            <button
              type="submit"
              disabled={submitting || !trimmed || tooLong}
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

      <AnimatePresence initial={false} mode="popLayout">
        {error ? (
          <motion.p
            key="error"
            id={errorId}
            role="alert"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="px-1 text-[13px] text-[var(--danger)]"
          >
            {error}
          </motion.p>
        ) : replaced !== null ? (
          <motion.p
            key="undo"
            role="status"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="px-1 flex items-center gap-1.5 text-[13px] text-[var(--fg-muted)]"
          >
            {replaced.by === "clear" ? "Text cleared." : "Your text was replaced by the example."}
            <button
              type="button"
              onClick={() => {
                setValue(replaced.text);
                setReplaced(null);
                textareaRef.current?.focus();
              }}
              className="font-medium text-[var(--fg-primary)] underline underline-offset-2 decoration-[var(--border-strong)] hover:decoration-[var(--fg-primary)] cursor-pointer"
            >
              Undo
            </button>
          </motion.p>
        ) : shortText ? (
          <motion.p
            key="short"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="px-1 text-[13px] text-[var(--fg-muted)]"
          >
            Short texts rarely match other reports. A full paragraph or the article's link works better.
          </motion.p>
        ) : null}
      </AnimatePresence>
    </form>
  );
}
