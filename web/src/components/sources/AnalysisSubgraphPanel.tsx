import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, ChevronDown, X } from "lucide-react";
import { describeError, getGraph } from "../../lib/api";
import type { Analysis, GraphPayload } from "../../lib/contracts";
import { LAYER_HINT, LAYER_LABEL, extractAnalysisSubgraph, sortKinds } from "../../lib/graph";
import { buttonClass, SECTION_LABEL, tagClass } from "../../lib/ui";
import { cn } from "../../lib/utils";
import { Favicon } from "../ui/Favicon";
import { Hint } from "../ui/Hint";
import { OutletInspector } from "./OutletInspector";
import { Tie } from "./TieEvidence";

const GraphMapView = lazy(() => import("./GraphMapView"));

const INITIAL_TIES = 4;

export interface AnalysisSubgraphPanelProps {
  readonly analysis: Analysis;
  readonly primaryDomain: string;
  readonly onClose: () => void;
}

export function AnalysisSubgraphPanel({
  analysis,
  primaryDomain,
  onClose,
}: Readonly<AnalysisSubgraphPanelProps>) {
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAllTies, setShowAllTies] = useState(false);
  const [inspectDomain, setInspectDomain] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getGraph(controller.signal)
      .then((g) => {
        setGraph(g);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (err instanceof Error && err.name === "AbortError") return;
        // Even if /api/graph fails, we can still show any live ties from `analysis` alongside the error.
        setError(describeError(err));
        setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const { focusDomain, subgraph, index, totalSites, totalClusterSites, directTies, cluster } = useMemo(
    () => extractAnalysisSubgraph(graph, analysis, primaryDomain),
    [graph, analysis, primaryDomain],
  );
  const visibleTies = showAllTies ? directTies : directTies.slice(0, INITIAL_TIES);
  const fullMapHref = focusDomain ? `/sources?outlet=${encodeURIComponent(focusDomain)}` : "/sources";

  return (
    <section
      id="analysis-source-network"
      aria-label="Source network for this analysis"
      className="editorial-card rounded-xl p-4 sm:p-5 space-y-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {focusDomain ? (
              <span className="inline-flex items-center gap-1.5 font-mono-num text-sm font-medium text-[var(--fg-primary)]">
                <Favicon domain={focusDomain} size={16} />
                {focusDomain}
              </span>
            ) : (
              <h2 className="text-sm font-medium text-[var(--fg-primary)]">Source network in this analysis</h2>
            )}
            {!loading && subgraph.edges.length > 0 && (
              <span className="font-mono-num text-xs text-[var(--fg-muted)]">
                {totalSites > subgraph.outlets.length
                  ? `top ${subgraph.outlets.length} of ${totalSites} sites`
                  : `${subgraph.outlets.length} ${subgraph.outlets.length === 1 ? "site" : "sites"}`}{" "}
                · {subgraph.edges.length} {subgraph.edges.length === 1 ? "tie" : "ties"}
              </span>
            )}
            {cluster && (
              <span className={tagClass("indigo", { mono: true })}>
                Group #{cluster.id} ·{" "}
                {totalClusterSites && totalClusterSites > cluster.outlets.length
                  ? `${cluster.outlets.length} of ${totalClusterSites} sites`
                  : `${cluster.outlets.length} sites`}
              </span>
            )}
          </div>
          <p className="text-xs text-[var(--fg-secondary)]">
            A tie is a shared technical or text trace between sites, never a verdict on either site.
          </p>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <Link to={fullMapHref} className={buttonClass("secondary", "sm")}>
            Full source map
            <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
          <button
            type="button"
            onClick={onClose}
            aria-label="Hide source network"
            className={buttonClass("ghost", "icon", "h-7 w-7")}
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
      </div>

      {error && (
        <p role="alert" className="text-xs text-[var(--danger)]">
          {error}
        </p>
      )}

      {loading ? (
        <div aria-busy="true" className="space-y-3">
          <div className="flex items-center gap-2 text-xs text-[var(--fg-muted)]">
            <span className="live-dot" aria-hidden="true" />
            <span className="shimmer">Loading source network</span>
          </div>
          <div className="h-[320px] rounded-xl bg-[var(--bg-subtle)] animate-pulse" />
        </div>
      ) : subgraph.edges.length === 0 ? (
        <p className="pt-2 border-t border-[var(--border-subtle)] text-[13px] text-[var(--fg-secondary)]">
          {focusDomain ? (
            <>
              <span className="font-mono-num text-[var(--fg-primary)]">{focusDomain}</span> shares no analytics tag,
              copied text, translation, operator, or link trace with other sites in the stored analyses.
            </>
          ) : (
            "No shared technical or text traces were found among the sites retrieved for this item."
          )}
        </p>
      ) : (
        <>
          {cluster && cluster.joined_by.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 text-xs text-[var(--fg-secondary)]">
              <span>Group joined by</span>
              {sortKinds(cluster.joined_by).map((kind) => (
                <Hint key={kind} content={LAYER_HINT[kind]}>
                  <span tabIndex={0} className={tagClass(kind === "link" ? "neutral" : "indigo")}>
                    {LAYER_LABEL[kind]}
                  </span>
                </Hint>
              ))}
              {cluster.listed > 0 && (
                <span className="text-[var(--fg-muted)]">
                  · {cluster.listed} of {cluster.outlets.length} on a published list
                </span>
              )}
            </div>
          )}

          <Suspense fallback={<div className="h-[360px] sm:h-[420px] rounded-xl bg-[var(--bg-subtle)] animate-pulse" />}>
            <GraphMapView
              graph={subgraph}
              index={index}
              needle={focusDomain ?? ""}
              onOpenOutlet={setInspectDomain}
              compact
            />
          </Suspense>

          {directTies.length > 0 && (
            <div className="pt-3 border-t border-[var(--border-subtle)] space-y-2">
              <h3 className={SECTION_LABEL}>
                {focusDomain ? `Direct ties of ${focusDomain}` : "Ties in this subgraph"}{" "}
                <span className="font-mono-num">({directTies.length})</span>
              </h3>
              <ul>
                {visibleTies.map((edge) => (
                  <Tie
                    key={`${edge.a}|${edge.b}`}
                    edge={edge}
                    from={focusDomain ?? undefined}
                    onOpenOutlet={setInspectDomain}
                  />
                ))}
              </ul>
              {directTies.length > INITIAL_TIES && (
                <button
                  type="button"
                  aria-expanded={showAllTies}
                  onClick={() => setShowAllTies((v) => !v)}
                  className={buttonClass("ghost", "sm", "-ml-2")}
                >
                  <ChevronDown
                    className={cn("h-3.5 w-3.5 transition-transform", showAllTies && "rotate-180")}
                    aria-hidden="true"
                  />
                  {showAllTies ? "Show fewer ties" : `Show all ${directTies.length} ties`}
                </button>
              )}
            </div>
          )}

          <OutletInspector
            index={index}
            domain={inspectDomain}
            onOpenOutlet={setInspectDomain}
            onClose={() => setInspectDomain(null)}
          />
        </>
      )}
    </section>
  );
}
