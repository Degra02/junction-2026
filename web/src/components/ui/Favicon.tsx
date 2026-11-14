import { useState } from "react";
import { cn } from "../../lib/utils";

export interface FaviconProps {
  readonly domain: string;
  readonly size?: number;
  readonly className?: string;
}

/**
 * Outlet icon from DuckDuckGo's favicon service; a lettered tile when the domain has none
 * or the service is unreachable.
 */
export function Favicon({ domain, size = 16, className }: Readonly<FaviconProps>) {
  const [failed, setFailed] = useState(false);
  const clean = domain.trim().toLowerCase();
  const letter = clean.replace(/^www\./, "").charAt(0).toUpperCase() || "?";
  const box = { width: size, height: size };

  if (!clean || failed) {
    return (
      <span
        aria-hidden="true"
        style={{ ...box, fontSize: Math.max(8, Math.round(size * 0.58)) }}
        className={cn(
          "inline-flex items-center justify-center shrink-0 rounded-[4px] bg-[var(--bg-subtle)] border border-[var(--border-subtle)] font-semibold text-[var(--fg-muted)] leading-none",
          className,
        )}
      >
        {letter}
      </span>
    );
  }

  return (
    <img
      src={`https://icons.duckduckgo.com/ip3/${encodeURIComponent(clean)}.ico`}
      alt=""
      aria-hidden="true"
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      width={size}
      height={size}
      style={box}
      onError={() => setFailed(true)}
      className={cn("shrink-0 rounded-[4px] bg-[var(--bg-surface)] object-contain", className)}
    />
  );
}

/** Overlapping row of outlet icons, for "found on 6 sites" summaries. */
export function FaviconStack({
  domains,
  max = 5,
  size = 16,
}: Readonly<{ domains: readonly string[]; max?: number; size?: number }>) {
  const shown = domains.slice(0, max);
  const extra = domains.length - shown.length;
  return (
    <span className="inline-flex items-center">
      {shown.map((d, i) => (
        <span
          key={d}
          className={cn("inline-flex rounded-[5px] ring-2 ring-[var(--bg-surface)]", i > 0 && "-ml-1")}
        >
          <Favicon domain={d} size={size} />
        </span>
      ))}
      {extra > 0 && (
        <span className="ml-1.5 text-[11px] font-mono-num text-[var(--fg-muted)]">+{extra}</span>
      )}
    </span>
  );
}
