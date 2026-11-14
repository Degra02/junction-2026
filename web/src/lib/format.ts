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

export function detectInputKind(raw: string): "url" | "text" {
  const trimmed = raw.trim();
  if (/^https?:\/\/\S+$/i.test(trimmed) && !trimmed.includes("\n")) {
    return "url";
  }
  return "text";
}
