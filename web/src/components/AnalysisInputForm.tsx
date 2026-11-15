import {
  useEffect,
  useId,
  useRef,
  useState,
  type ClipboardEvent,
  type DragEvent,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import * as Popover from "@radix-ui/react-popover";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, Check, ChevronDown, ImagePlus, Link2, Loader2, X } from "lucide-react";
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
  readonly contextUrl?: string;
  readonly lang?: string;
  readonly autoSubmit?: boolean;
  readonly nonce: number;
}

export interface AnalysisInputFormProps {
  readonly prefill?: PrefillValue | null;
}

interface AttachedImage {
  readonly dataUri: string;
  readonly name: string;
  readonly width: number;
  readonly height: number;
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
const MAX_IMAGE_DIM = 1280;
const MAX_DATA_URI_LENGTH = 420_000;

const IS_MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

async function compressImageFile(file: File): Promise<AttachedImage> {
  if (!file.type.startsWith("image/")) {
    throw new Error("Choose a PNG, JPEG, WebP or GIF image.");
  }
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new Error("Could not decode that image file.");
  }
  try {
    const scale = Math.min(1, MAX_IMAGE_DIM / Math.max(bitmap.width || 1, bitmap.height || 1));
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      throw new Error("Canvas image compression is unavailable in this browser.");
    }
    ctx.drawImage(bitmap, 0, 0, width, height);

    for (const [mime, quality] of [
      ["image/webp", 0.84],
      ["image/webp", 0.68],
      ["image/jpeg", 0.8],
      ["image/jpeg", 0.62],
    ] as const) {
      const dataUri = canvas.toDataURL(mime, quality);
      if (dataUri.startsWith(`data:${mime};base64,`) && dataUri.length <= MAX_DATA_URI_LENGTH) {
        return { dataUri, name: file.name || "pasted-image", width, height };
      }
    }
    throw new Error("That image is too detailed; crop it to the meme or post and try again.");
  } finally {
    bitmap.close();
  }
}

export function AnalysisInputForm({ prefill }: Readonly<AnalysisInputFormProps>) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const inputId = useId();
  const contextUrlId = useId();
  const customLangId = useId();
  const errorId = useId();
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const autoSubmittedNonceRef = useRef<number | null>(null);

  const [value, setValue] = useState("");
  const [attachedImage, setAttachedImage] = useState<AttachedImage | null>(null);
  const [contextUrl, setContextUrl] = useState("");
  const [dragging, setDragging] = useState(false);
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
  // Text the user had before a prefill or Clear replaced it, for Undo.
  const [replaced, setReplaced] = useState<{ text: string; by: "prefill" | "clear" } | null>(null);
  const valueRef = useRef(value);
  valueRef.current = value;

  useEffect(() => {
    if (!prefill) return;
    const nextValue = prefill.value;
    const nextKind: "auto" | InputKind = prefill.kind ?? "auto";
    const nextContextUrl = (prefill.contextUrl ?? "").trim();
    const nextLang = (prefill.lang ?? "").trim().toLowerCase();
    const knownCodes = new Set(EXPLANATION_LANGUAGE_OPTIONS.map((o) => o.code));

    if (nextKind === "image") {
      setAttachedImage({
        dataUri: nextValue,
        name: cleanDomain(nextValue) || "shared-image",
        width: 0,
        height: 0,
      });
      setContextUrl(nextContextUrl);
      setValue("");
    } else {
      const previous = valueRef.current;
      setReplaced(
        previous.trim() && previous !== nextValue ? { text: previous, by: "prefill" } : null,
      );
      setAttachedImage(null);
      setValue(nextValue);
      setContextUrl(nextContextUrl);
      setKindOverride(nextKind);
    }

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
      if (!clean) return;
      const resolvedKind: InputKind =
        nextKind === "image" ? "image" : nextKind === "auto" ? detectInputKind(clean) : nextKind;
      const submitted = resolvedKind === "url" ? withScheme(clean) : clean;
      if (resolvedKind === "url" && !/^https?:\/\/\S+$/i.test(submitted)) {
        setError("That is not a link. Switch to Text to analyse it as text.");
        return;
      }
      const cleanCtx = nextContextUrl ? withScheme(nextContextUrl) : null;
      setSubmitting(true);
      createAnalysis({
        kind: resolvedKind,
        value: submitted,
        context_url: cleanCtx,
        explanation_language: nextLang || null,
      })
        .then((created) => {
          navigate(`/analyses/${created.id}`, { replace: true });
        })
        .catch((err: unknown) => {
          setError(describeError(err));
          setSubmitting(false);
        });
      return;
    }

    if (nextKind !== "image") {
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
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
  }, [value, attachedImage]);

  async function handleImageFile(file: File) {
    setError(null);
    try {
      const compressed = await compressImageFile(file);
      setAttachedImage(compressed);
      // If the user already pasted a post/article link into the box, move it automatically into
      // the side-by-side companion link field!
      const currentTrimmed = value.trim();
      if (currentTrimmed && !contextUrl.trim() && detectInputKind(currentTrimmed) === "url") {
        setContextUrl(withScheme(currentTrimmed));
        setValue("");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not read that image.");
    }
  }

  function handlePaste(e: ClipboardEvent<HTMLElement>) {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of items) {
      if (item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (file) {
          e.preventDefault();
          void handleImageFile(file);
          return;
        }
      }
    }
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer?.files?.[0];
    if (file && file.type.startsWith("image/")) {
      void handleImageFile(file);
    }
  }

  const trimmed = value.trim();
  const hasImage = attachedImage !== null;
  const effectiveKind: InputKind = hasImage
    ? "image"
    : kindOverride === "auto"
      ? detectInputKind(trimmed)
      : kindOverride;
  const wordCount = trimmed ? trimmed.split(/\s+/).length : 0;
  const charCount = Array.from(trimmed).length;
  const urlDomain = effectiveKind === "url" && trimmed ? cleanDomain(trimmed) : "";
  const contextTrimmed = contextUrl.trim();
  const contextDomain =
    contextTrimmed && contextTrimmed.includes(".") ? cleanDomain(withScheme(contextTrimmed)) : "";
  const resolvedLanguage =
    langChoice === "__custom__" ? customLang.trim().toLowerCase() : langChoice;
  const singleLineUrl = effectiveKind === "url" && !trimmed.includes("\n");
  const tooLong = effectiveKind === "text" && charCount > MAX_TEXT_CHARS;
  const shortText = effectiveKind === "text" && wordCount > 0 && wordCount < SHORT_TEXT_WORDS;

  async function submitCurrentInput() {
    setError(null);
    if (langChoice === "__custom__" && resolvedLanguage && !/^[a-z]{2,3}$/i.test(resolvedLanguage)) {
      setError("Use a 2- or 3-letter language code, like fi or cs.");
      return;
    }

    let normalizedContextUrl: string | null = null;
    if (contextTrimmed) {
      const withHttp = withScheme(contextTrimmed);
      if (!/^https?:\/\/\S+$/i.test(withHttp)) {
        setError("The attached post/article link must be a valid http(s) URL.");
        return;
      }
      normalizedContextUrl = withHttp;
    }

    if (hasImage && attachedImage) {
      setSubmitting(true);
      try {
        const created = await createAnalysis(
          {
            kind: "image",
            value: attachedImage.dataUri,
            context_url: normalizedContextUrl,
            explanation_language: resolvedLanguage || null,
          },
          { force },
        );
        navigate(`/analyses/${created.id}`);
      } catch (err: unknown) {
        setError(describeError(err));
        setSubmitting(false);
      }
      return;
    }

    if (!trimmed) {
      setError("Paste a link, text, or drop a meme/screenshot first.");
      textareaRef.current?.focus();
      return;
    }
    const submitted = effectiveKind === "url" ? withScheme(trimmed) : trimmed;
    if (effectiveKind === "url" && !/^https?:\/\/\S+$/i.test(submitted)) {
      setError("That is not a link. Switch to Text to analyse it as text.");
      return;
    }
    if (tooLong) {
      setError(
        `The text has ${charCount.toLocaleString("en")} characters; the limit is ${MAX_TEXT_CHARS.toLocaleString("en")}. Shorten it, or paste the article's link instead.`,
      );
      return;
    }

    setSubmitting(true);
    try {
      const created = await createAnalysis(
        {
          kind: effectiveKind,
          value: submitted,
          context_url: normalizedContextUrl,
          explanation_language: resolvedLanguage || null,
        },
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

  function handleKeyDown(e: KeyboardEvent<HTMLElement>) {
    if (e.key !== "Enter" || submitting) return;
    if (e.metaKey || e.ctrlKey || (!e.shiftKey && singleLineUrl && trimmed.length > 0)) {
      e.preventDefault();
      void submitCurrentInput();
    }
  }

  const kindLabel = hasImage
    ? "Image / meme"
    : !trimmed
      ? kindOverride === "auto"
        ? "Link, text, or meme"
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
      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        className="sr-only"
        tabIndex={-1}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void handleImageFile(file);
          e.target.value = "";
        }}
      />

      <div
        data-spotlight
        onPaste={handlePaste}
        onDragOver={(e) => {
          e.preventDefault();
          if (!dragging) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={cn(
          "omnibox-shell rounded-2xl transition-colors",
          dragging && "ring-2 ring-[var(--accent)] bg-[var(--accent-soft)]/30",
        )}
      >
        {hasImage && attachedImage ? (
          <div className="p-3.5 sm:p-4 grid grid-cols-1 sm:grid-cols-[148px_1fr] gap-4 items-start">
            <div className="relative group rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)] overflow-hidden flex items-center justify-center min-h-[112px]">
              <img
                src={attachedImage.dataUri}
                alt="Uploaded meme or screenshot preview"
                className="max-h-36 w-full object-contain"
              />
              <button
                type="button"
                disabled={submitting}
                onClick={() => {
                  setAttachedImage(null);
                  setError(null);
                  requestAnimationFrame(() => textareaRef.current?.focus());
                }}
                aria-label="Remove image"
                title="Remove image"
                className="absolute top-1.5 right-1.5 h-6 w-6 rounded-full bg-[var(--bg-surface)]/90 border border-[var(--border-subtle)] text-[var(--fg-primary)] inline-flex items-center justify-center shadow-sm hover:bg-[var(--bg-surface)] cursor-pointer"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
              {attachedImage.width > 0 && (
                <span className="absolute bottom-1.5 left-1.5 rounded bg-[var(--bg-surface)]/85 px-1.5 py-0.5 font-mono-num text-[10px] text-[var(--fg-secondary)]">
                  {attachedImage.width}×{attachedImage.height}
                </span>
              )}
            </div>

            <div className="space-y-2 min-w-0">
              <label
                htmlFor={contextUrlId}
                className="flex items-center gap-1.5 text-xs font-medium text-[var(--fg-primary)]"
              >
                <Link2 className="h-3.5 w-3.5 text-[var(--accent)] shrink-0" aria-hidden="true" />
                <span>Attached social post, comment, or article link</span>
                <span className="text-[var(--fg-muted)] font-normal">(optional)</span>
              </label>

              <div className="relative flex items-center">
                {contextDomain && (
                  <span className="pl-2.5 pr-1 flex items-center pointer-events-none">
                    <Favicon domain={contextDomain} size={14} />
                  </span>
                )}
                <input
                  id={contextUrlId}
                  type="url"
                  value={contextUrl}
                  onChange={(e) => {
                    setContextUrl(e.target.value);
                    if (error) setError(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !submitting) {
                      e.preventDefault();
                      void submitCurrentInput();
                    }
                  }}
                  disabled={submitting}
                  placeholder="https://x.com/… · reddit.com/… · t.me/… · article URL"
                  className={cn(
                    "w-full h-9 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] pr-8 text-[13px] font-mono-num text-[var(--fg-primary)] placeholder:font-sans placeholder:text-[var(--fg-muted)] outline-none focus:border-[var(--accent)]",
                    contextDomain ? "pl-1.5" : "pl-3",
                  )}
                />
                {contextUrl && !submitting && (
                  <button
                    type="button"
                    onClick={() => setContextUrl("")}
                    aria-label="Clear companion link"
                    className="absolute right-1.5 h-6 w-6 inline-flex items-center justify-center rounded text-[var(--fg-muted)] hover:text-[var(--fg-primary)] cursor-pointer"
                  >
                    <X className="h-3 w-3" aria-hidden="true" />
                  </button>
                )}
              </div>

              <p className="text-[11.5px] text-[var(--fg-muted)] leading-relaxed">
                Adds the post caption, author, timestamp, and publishing domain so the pipeline
                verifies both the meme/screenshot and the thread sharing it.
              </p>
            </div>
          </div>
        ) : (
          <>
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
                placeholder="Paste an article link, any text, or paste / drop a meme or screenshot…"
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
          </>
        )}

        <div className="flex items-center justify-between gap-2 px-2.5 pb-2.5">
          <div className="flex items-center gap-0.5 min-w-0">
            {!hasImage ? (
              <Popover.Root open={modeOpen} onOpenChange={setModeOpen}>
                <Popover.Trigger asChild>
                  <button type="button" className={buttonClass("ghost", "sm", "max-w-[220px]")}>
                    {effectiveKind === "url" && urlDomain && (
                      <Favicon domain={urlDomain} size={14} />
                    )}
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
            ) : (
              <span className="inline-flex items-center gap-1.5 h-7 px-2.5 text-xs font-medium text-[var(--accent)]">
                <ImagePlus className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Image / meme</span>
              </span>
            )}

            <button
              type="button"
              disabled={submitting}
              onClick={() => fileInputRef.current?.click()}
              className={buttonClass("ghost", "sm")}
              title="Upload or replace a meme or screenshot (or press Ctrl+V)"
            >
              <ImagePlus className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="hidden sm:inline">{hasImage ? "Replace" : "Image"}</span>
            </button>

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
            {!hasImage && (
              <kbd className="hidden sm:inline text-[11px] font-mono-num text-[var(--fg-muted)]">
                {singleLineUrl ? "↵" : IS_MAC ? "⌘↵" : "Ctrl ↵"}
              </kbd>
            )}
            <button
              type="submit"
              disabled={submitting || (!hasImage && (!trimmed || tooLong))}
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
            {replaced.by === "clear" ? "Text cleared." : "Your text was replaced."}
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
            Short texts rarely match other reports. A full paragraph or the article's link works
            better.
          </motion.p>
        ) : null}
      </AnimatePresence>
    </form>
  );
}
