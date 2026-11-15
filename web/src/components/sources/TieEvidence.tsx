import { ArrowRight, ExternalLink } from "lucide-react";
import type { GraphEdge, GraphLayer } from "../../lib/contracts";
import {
  LAYER_HINT,
  LAYER_LABEL,
  idKind,
  isIdEvidence,
  isLinkEvidence,
  isPairEvidence,
  isSingleTagTie,
  shortUrl,
  sortLayers,
} from "../../lib/graph";
import { tagClass } from "../../lib/ui";
import { cn } from "../../lib/utils";
import { Favicon } from "../ui/Favicon";
import { Hint, InfoHint } from "../ui/Hint";

const WEIGHT_HINT =
  "How much the shared traces add up, from 0 to 1. Analytics IDs and copied text weigh most; ad accounts and links least; one story counts less than several. It measures the evidence of a relationship, not either site.";

export interface TieProps {
  readonly edge: GraphEdge;
  /** The outlet the tie is seen from: only the other end is named. Both ends when omitted. */
  readonly from?: string;
  readonly onOpenOutlet?: (domain: string) => void;
}

/** One tie with every piece of its evidence inline: IDs, article pairs, links. */
export function Tie({ edge, from, onOpenOutlet }: Readonly<TieProps>) {
  const ends = from ? [from === edge.a ? edge.b : edge.a] : [edge.a, edge.b];
  return (
    <li className="py-3 border-t border-[var(--border-subtle)] first:border-t-0 space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5 min-w-0">
          {ends.map((domain, i) => (
            <span key={domain} className="inline-flex items-center gap-1.5">
              {i > 0 && <span className="text-[var(--fg-muted)] text-xs">and</span>}
              <OutletButton domain={domain} onOpen={onOpenOutlet} />
            </span>
          ))}
        </div>
        <span className="inline-flex items-center gap-1 text-xs text-[var(--fg-muted)]">
          <span className="font-mono-num text-[var(--fg-secondary)]">{edge.coordination.toFixed(2)}</span>
          <InfoHint label="Evidence weight" content={WEIGHT_HINT} />
        </span>
      </div>
      <ul className="space-y-1.5">
        {sortLayers(edge.layers).map((layer) => (
          <LayerLine key={layer.kind} layer={layer} />
        ))}
      </ul>
      {isSingleTagTie(edge) && (
        <p className="text-xs text-[var(--fg-muted)]">
          One shared ID seen on one article: the thinnest evidence kept in the graph.
        </p>
      )}
    </li>
  );
}

function LayerLine({ layer }: Readonly<{ layer: GraphLayer }>) {
  const evidence = layer.evidence ?? [];
  return (
    <li className="flex flex-wrap items-start gap-x-2 gap-y-1 text-[13px]">
      <Hint content={LAYER_HINT[layer.kind]}>
        <span tabIndex={0} className={tagClass(layer.kind === "link" ? "neutral" : "indigo")}>
          {LAYER_LABEL[layer.kind]}
        </span>
      </Hint>
      {layer.count !== undefined && (
        <span className="text-xs text-[var(--fg-muted)] pt-0.5">
          {layer.count} {layer.count === 1 ? "article" : "articles"}
        </span>
      )}
      {evidence.length > 0 && (
        <ul className="basis-full space-y-1 pl-1">
          {evidence.map((e, i) => {
            if (isIdEvidence(e)) {
              return (
                <li key={e.id} className="flex items-center gap-2">
                  <code className="font-mono-num text-xs text-[var(--fg-primary)] select-all">{e.id}</code>
                  <span className="text-xs text-[var(--fg-muted)]">{idKind(e.id)}</span>
                </li>
              );
            }
            if (isPairEvidence(e)) {
              const measure =
                e.share !== undefined
                  ? `${Math.round(e.share * 100)}% of the wording shared`
                  : e.similarity !== undefined
                    ? `${Math.round(e.similarity * 100)}% similar meaning`
                    : null;
              return (
                <li key={`${e.a}|${e.b}|${i}`} className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs">
                  <ArticleLink url={e.a} />
                  <ArrowRight className="h-3 w-3 text-[var(--fg-muted)]" aria-label="and" />
                  <ArticleLink url={e.b} />
                  {measure && <span className="text-[var(--fg-muted)]">· {measure}</span>}
                </li>
              );
            }
            if (isLinkEvidence(e)) {
              return (
                <li key={`${e.from}|${e.to}`} className="text-xs text-[var(--fg-secondary)]">
                  <span className="font-mono-num">{e.from}</span> links to{" "}
                  <span className="font-mono-num">{e.to}</span>
                </li>
              );
            }
            return null;
          })}
        </ul>
      )}
    </li>
  );
}

function ArticleLink({ url }: Readonly<{ url: string }>) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 font-mono-num text-[var(--accent)] hover:underline break-all"
    >
      {shortUrl(url)}
      <ExternalLink className="h-3 w-3 shrink-0" aria-label="(opens in a new tab)" />
    </a>
  );
}

export function OutletButton({
  domain,
  onOpen,
  className,
}: Readonly<{ domain: string; onOpen?: (domain: string) => void; className?: string }>) {
  const body = (
    <>
      <Favicon domain={domain} size={14} />
      <span className="font-mono-num text-[13px] truncate">{domain}</span>
    </>
  );
  if (!onOpen) {
    return <span className={cn("inline-flex items-center gap-1.5 min-w-0", className)}>{body}</span>;
  }
  return (
    <button
      type="button"
      onClick={() => onOpen(domain)}
      className={cn(
        "inline-flex items-center gap-1.5 min-w-0 rounded-md px-1 -mx-1 text-[var(--fg-primary)] hover:bg-[var(--bg-hover)] cursor-pointer",
        className,
      )}
    >
      {body}
    </button>
  );
}
