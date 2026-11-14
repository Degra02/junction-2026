import { cn } from "./utils";

/** Shared control styles. Use these instead of hand-rolled button/tag classes. */

export type ButtonVariant = "primary" | "secondary" | "ghost" | "accent";
export type ButtonSize = "sm" | "md" | "lg" | "icon";

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-1.5 font-medium whitespace-nowrap select-none transition-[background-color,border-color,color,box-shadow,transform] duration-150 active:translate-y-px disabled:opacity-45 disabled:pointer-events-none cursor-pointer";

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  primary:
    "bg-[var(--btn-primary-bg)] text-[var(--btn-primary-fg)] hover:bg-[var(--btn-primary-hover)] shadow-[var(--shadow-editorial)]",
  secondary:
    "bg-[var(--bg-surface)] text-[var(--fg-primary)] border border-[var(--border-subtle)] hover:border-[var(--border-strong)] hover:bg-[var(--bg-subtle)] shadow-[var(--shadow-editorial)]",
  ghost:
    "text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]",
  accent: "bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] dark:text-[#09090a]",
};

const BUTTON_SIZE: Record<ButtonSize, string> = {
  sm: "h-7 px-2.5 text-xs rounded-md",
  md: "h-8 px-3 text-[13px] rounded-lg",
  lg: "h-10 px-4 text-sm rounded-lg",
  icon: "h-8 w-8 rounded-lg",
};

export function buttonClass(
  variant: ButtonVariant = "secondary",
  size: ButtonSize = "md",
  extra?: string,
): string {
  return cn(BUTTON_BASE, BUTTON_VARIANT[variant], BUTTON_SIZE[size], extra);
}

export type Tone = "neutral" | "accent" | "indigo" | "teal" | "caution" | "danger";

const TAG_TONE: Record<Tone, string> = {
  neutral: "bg-[var(--bg-subtle)] text-[var(--fg-secondary)] border-[var(--border-subtle)]",
  accent: "bg-[var(--accent-soft)] text-[var(--accent)] border-[var(--accent-border)]",
  indigo: "bg-[var(--indigo-soft)] text-[var(--indigo)] border-transparent",
  teal: "bg-[var(--teal-soft)] text-[var(--teal)] border-[var(--teal-border)]",
  caution: "bg-[var(--caution-soft)] text-[var(--caution)] border-[var(--caution-border)]",
  danger: "bg-[var(--danger-soft)] text-[var(--danger)] border-[var(--danger-border)]",
};

/** Small status/metadata label. `mono` for domains, codes and numbers. */
export function tagClass(tone: Tone = "neutral", options?: { readonly mono?: boolean }, extra?: string): string {
  return cn(
    "inline-flex items-center gap-1 h-5 px-1.5 rounded-md border text-[11px] font-medium leading-none whitespace-nowrap",
    options?.mono && "font-mono-num",
    TAG_TONE[tone],
    extra,
  );
}

/** Small uppercase-free section label above a group ("Sources", "Claims"). */
export const SECTION_LABEL = "text-xs font-medium text-[var(--fg-muted)]";
