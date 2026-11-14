export function formatPct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "n/a";
  }
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatCi(ci: readonly [number, number] | null | undefined, digits = 0): string {
  if (!ci) return "";
  return `[${(ci[0] * 100).toFixed(digits)}%, ${(ci[1] * 100).toFixed(digits)}%]`;
}

export function formatSignedContribution(value: number): string {
  if (Math.abs(value) < 0.005) return "0.00";
  return value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2);
}

export function formatDurationMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function formatShortDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-GB", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDomainAge(
  registeredAt: string | null | undefined,
  firstCertAt: string | null | undefined,
  referenceIso?: string | null,
): string | null {
  const originIso = registeredAt ?? firstCertAt;
  if (!originIso) return null;
  const origin = new Date(originIso);
  if (Number.isNaN(origin.getTime())) return null;
  const ref = referenceIso ? new Date(referenceIso) : new Date();
  const baseMs = Number.isNaN(ref.getTime()) ? Date.now() : ref.getTime();
  const days = Math.max(0, Math.floor((baseMs - origin.getTime()) / 86_400_000));
  if (days < 60) return `${days}d domain`;
  if (days < 365) return `${Math.round(days / 30)}mo domain`;
  const years = Math.floor(days / 365);
  return `${years}y domain`;
}

/** A link pasted without its scheme: `www.ansa.it/…`, `ansa.it/sito/…`. */
const BARE_LINK_RE = /^(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}(?:[/?#]\S*)?$/i;

export function detectInputKind(raw: string): "url" | "text" {
  const trimmed = raw.trim();
  if (/\s/.test(trimmed)) return "text";
  return /^https?:\/\/\S+$/i.test(trimmed) || BARE_LINK_RE.test(trimmed) ? "url" : "text";
}

/** The link as the API needs it: `https://` added when it was pasted without a scheme. */
export function withScheme(link: string): string {
  return /^https?:\/\//i.test(link) ? link : `https://${link}`;
}

/** "3 min ago", "2 h ago", "yesterday", or a date for anything older than a week. */
export function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const minutes = Math.round((Date.now() - then) / 60_000);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (minutes < 1) return "just now";
  if (minutes < 60) return rtf.format(-minutes, "minute");
  if (minutes < 60 * 24) return rtf.format(-Math.round(minutes / 60), "hour");
  if (minutes < 60 * 24 * 7) return rtf.format(-Math.round(minutes / 1440), "day");
  return formatShortDate(iso) ?? "";
}
