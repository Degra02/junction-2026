import { useState } from "react";
import { Link } from "react-router-dom";
import { FileText } from "lucide-react";
import { formatRelativeTime } from "../lib/format";
import { clearRecent, loadRecent } from "../lib/recent";
import { SECTION_LABEL } from "../lib/ui";
import { Favicon } from "./ui/Favicon";

/** The analyses this browser opened, so they can be found again without keeping the link. */
export function RecentAnalyses() {
  const [items, setItems] = useState(loadRecent);
  if (items.length === 0) return null;

  return (
    <section aria-labelledby="recent-heading" className="space-y-1.5">
      <div className="flex items-center justify-between px-1">
        <h2 id="recent-heading" className={SECTION_LABEL}>
          Recent
        </h2>
        <button
          type="button"
          onClick={() => {
            clearRecent();
            setItems([]);
          }}
          className="text-xs text-[var(--fg-muted)] hover:text-[var(--fg-primary)] cursor-pointer"
        >
          Clear
        </button>
      </div>
      <ul className="divide-y divide-[var(--border-subtle)] border-y border-[var(--border-subtle)]">
        {items.map((item) => (
          <li key={item.id}>
            <Link
              to={`/analyses/${item.id}`}
              className="flex items-center gap-2.5 h-10 px-1 text-[13px] text-[var(--fg-primary)] hover:bg-[var(--bg-hover)] transition-colors"
            >
              {item.domain ? (
                <Favicon domain={item.domain} size={14} />
              ) : (
                <FileText className="h-3.5 w-3.5 shrink-0 text-[var(--fg-muted)]" aria-hidden="true" />
              )}
              <span className="truncate flex-1">{item.title}</span>
              <span className="shrink-0 text-xs text-[var(--fg-muted)]">{formatRelativeTime(item.at)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
