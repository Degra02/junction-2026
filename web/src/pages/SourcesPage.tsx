import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ChevronDown, ExternalLink, Search } from "lucide-react";
import { OutletInspector } from "../components/sources/OutletInspector";
import { OutletButton, Tie } from "../components/sources/TieEvidence";
import { describeError, getGraph } from "../lib/api";
import type { GraphCluster, GraphPayload } from "../lib/contracts";
import { LAYER_HINT, LAYER_LABEL, clusterTies, indexGraph, sortKinds } from "../lib/graph";
import { Hint } from "../components/ui/Hint";
import { buttonClass, tagClass } from "../lib/ui";
import { cn } from "../lib/utils";

/** Where a reader asks for a correction (graph rule 2). */
const CORRECTIONS_URL = "https://github.com/Degra02/junction-2026/issues/new?title=Source%20graph%20correction";
const OUTLET_PAGE = 50;

export type SourcesPageProps = Record<string, never>;

export function SourcesPage(_props: Readonly<SourcesPageProps>) {
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [shown, setShown] = useState(OUTLET_PAGE);
  const [params, setParams] = useSearchParams();
  const openDomain = params.get("outlet");

  useEffect(() => {
    const controller = new AbortController();
    getGraph(controller.signal)
      .then((g) => {
        setGraph(g);
        setMissing(g === null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (err instanceof Error && err.name === "AbortError") return;
        setError(describeError(err));
        setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const index = useMemo(() => (graph ? indexGraph(graph) : null), [graph]);

  // The open outlet lives in the URL (`?outlet=`): Back closes it, a link opens it.
  const openOutlet = useCallback(
    (domain: string) => setParams((p) => ({ ...Object.fromEntries(p), outlet: domain })),
    [setParams],
  );
  const closeOutlet = useCallback(
    () =>
      setParams((p) => {
        const next = new URLSearchParams(p);
        next.delete("outlet");
        return next;
      }),
    [setParams],
  );

  const needle = query.trim().toLowerCase();
  const clusters = useMemo(() => {
    if (!graph) return [];
    return graph.clusters.filter((c) => !needle || c.outlets.some((d) => d.includes(needle)));
  }, [graph, needle]);
  const outlets = useMemo(() => {
    if (!graph || !index) return [];
    return graph.outlets
      .filter((o) => !needle || o.domain.includes(needle) || o.operator.includes(needle))
      .map((o) => ({ outlet: o, ties: index.ties.get(o.domain)?.length ?? 0 }))
      .sort((x, y) => y.ties - x.ties || x.outlet.domain.localeCompare(y.outlet.domain));
  }, [graph, index, needle]);

  return (
    <div className="space-y-8">
      <header className="space-y-1">
        <h1 className="display text-3xl text-[var(--fg-primary)]">Sources</h1>
        <p className="text-sm text-[var(--fg-secondary)]">
          Sites that share a technical or editorial trace in the analyses we have stored.
        </p>
      </header>

      <Notice />

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-[var(--danger-border)] bg-[var(--danger-soft)] px-3 py-2 text-[13px] text-[var(--danger)]"
        >
          {error}
        </p>
      )}

      {loading && (
        <div className="space-y-4" aria-busy="true">
          <div className="h-6 w-64 rounded-md bg-[var(--bg-subtle)] animate-pulse" />
          <div className="h-48 rounded-xl bg-[var(--bg-subtle)] animate-pulse" />
        </div>
      )}

      {missing && (
        <p className="text-sm text-[var(--fg-secondary)]">The source graph is not published yet.</p>
      )}

      {graph && index && (
        <>
          <Counts graph={graph} />

          <label className="relative block max-w-md">
            <span className="sr-only">Find a site</span>
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--fg-muted)]"
              aria-hidden="true"
            />
            <input
              type="search"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setShown(OUTLET_PAGE);
              }}
              placeholder="Find a site, e.g. kxan.com"
              className="h-9 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] pl-8 pr-3 text-[13px] outline-none focus:border-[var(--accent)]"
            />
          </label>

          <section className="space-y-3">
            <h2 className="text-sm font-medium">
              Groups <span className="font-mono-num text-[var(--fg-muted)]">{clusters.length}</span>
            </h2>
            {clusters.length === 0 ? (
              <p className="text-[13px] text-[var(--fg-secondary)]">No group contains “{query}”.</p>
            ) : (
              <ul className="space-y-3">
                {clusters.map((cluster) => (
                  <ClusterCard key={cluster.id} graph={graph} cluster={cluster} onOpenOutlet={openOutlet} />
                ))}
              </ul>
            )}
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-medium">
              All sites <span className="font-mono-num text-[var(--fg-muted)]">{outlets.length}</span>
            </h2>
            <div className="editorial-card rounded-xl overflow-x-auto">
              <table className="w-full border-collapse text-left text-[13px]">
                <thead>
                  <tr className="border-b border-[var(--border-subtle)] text-xs text-[var(--fg-muted)]">
                    <th className="px-4 py-2 font-medium">Site</th>
                    <th className="px-4 py-2 font-medium">Operator</th>
                    <th className="px-4 py-2 font-medium text-right">Ties</th>
                    <th className="px-4 py-2 font-medium text-right">Group</th>
                    <th className="px-4 py-2 font-medium text-right">Articles</th>
                  </tr>
                </thead>
                <tbody>
                  {outlets.slice(0, shown).map(({ outlet, ties }) => (
                    <tr key={outlet.domain} className="border-t border-[var(--border-subtle)] hover:bg-[var(--bg-hover)]">
                      <td className="px-4 py-1.5">
                        <OutletButton domain={outlet.domain} onOpen={openOutlet} />
                      </td>
                      <td className="px-4 py-1.5 font-mono-num text-[var(--fg-secondary)]">{outlet.operator}</td>
                      <td className="px-4 py-1.5 font-mono-num text-right">{ties}</td>
                      <td className="px-4 py-1.5 font-mono-num text-right text-[var(--fg-secondary)]">
                        {outlet.cluster === null ? "–" : `#${outlet.cluster}`}
                      </td>
                      <td className="px-4 py-1.5 font-mono-num text-right text-[var(--fg-secondary)]">
                        {outlet.articles}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {outlets.length > shown && (
              <button type="button" onClick={() => setShown((n) => n + OUTLET_PAGE)} className={buttonClass("secondary", "md")}>
                Show {Math.min(OUTLET_PAGE, outlets.length - shown)} more
              </button>
            )}
          </section>

          <OutletInspector index={index} domain={openDomain} onOpenOutlet={openOutlet} onClose={closeOutlet} />
        </>
      )}
    </div>
  );
}

/** Rule 2 of the graph tasks: a tie is a relationship, never a verdict; how to correct one. */
function Notice() {
  return (
    <aside className="editorial-card rounded-xl p-4 sm:p-5 space-y-2 text-sm text-[var(--fg-secondary)]">
      <p className="font-medium text-[var(--fg-primary)]">A tie is a relationship, not a verdict.</p>
      <p>
        Two sites are tied when they share a trace we can show you: the same operator, the same analytics or ad
        tag, copied or translated text, or a link. It says nothing about whether either site is reliable, and no
        site gets a score. That is why the UN (un.org, reliefweb.int), AFP's fact-check editions and Nexstar's
        local newsrooms appear here next to RT's mirror sites and the news-pravda.com editions.
      </p>
      <p>
        A tie looks wrong?{" "}
        <a
          href={CORRECTIONS_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[var(--accent)] hover:underline"
        >
          Ask for a correction
          <ExternalLink className="h-3 w-3" aria-label="(opens in a new tab)" />
        </a>{" "}
        with the two sites and what you found.
      </p>
    </aside>
  );
}

function Counts({ graph }: Readonly<{ graph: GraphPayload }>) {
  const items: Array<[string, number]> = [
    ["sites", graph.counts.outlets],
    ["ties", graph.counts.edges],
    ["groups", graph.counts.clusters],
    ["articles", graph.counts.articles],
  ];
  const built = new Date(graph.built_at);
  return (
    <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
      {items.map(([label, value]) => (
        <span key={label} className="text-[13px] text-[var(--fg-secondary)]">
          <span className="tabular font-semibold tracking-tight text-xl text-[var(--fg-primary)]">
            {value.toLocaleString()}
          </span>{" "}
          {label}
        </span>
      ))}
      <span className="text-xs text-[var(--fg-muted)]">
        from {graph.counts.analyses} stored analyses, built{" "}
        {Number.isNaN(built.getTime()) ? graph.built_at : built.toLocaleString()}
      </span>
    </div>
  );
}

function ClusterCard({
  graph,
  cluster,
  onOpenOutlet,
}: Readonly<{ graph: GraphPayload; cluster: GraphCluster; onOpenOutlet: (domain: string) => void }>) {
  const [open, setOpen] = useState(false);
  const ties = useMemo(() => clusterTies(graph, cluster), [graph, cluster]);
  const tieCount = ties.length;

  return (
    <li className="editorial-card rounded-xl p-4 sm:p-5 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono-num text-xs text-[var(--fg-muted)]">#{cluster.id}</span>
        <span className="text-[13px] text-[var(--fg-secondary)]">
          {cluster.outlets.length} sites joined by
        </span>
        {sortKinds(cluster.joined_by).map((kind) => (
          <Hint key={kind} content={LAYER_HINT[kind]}>
            <span tabIndex={0} className={tagClass(kind === "link" ? "neutral" : "indigo")}>
              {LAYER_LABEL[kind]}
            </span>
          </Hint>
        ))}
        {cluster.listed > 0 && (
          <span className="text-xs text-[var(--fg-muted)]">
            · {cluster.listed} of {cluster.outlets.length} on a published list
          </span>
        )}
      </div>
      <ul className="flex flex-wrap gap-x-3 gap-y-1">
        {cluster.outlets.map((domain) => (
          <li key={domain}>
            <OutletButton domain={domain} onOpen={onOpenOutlet} />
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className={buttonClass("ghost", "sm", "-ml-2")}
      >
        <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} aria-hidden="true" />
        {open ? "Hide the evidence" : `Show the evidence (${tieCount} ${tieCount === 1 ? "tie" : "ties"})`}
      </button>
      {open && (
        <ul>
          {ties.map((edge) => (
            <Tie key={`${edge.a}|${edge.b}`} edge={edge} onOpenOutlet={onOpenOutlet} />
          ))}
        </ul>
      )}
    </li>
  );
}
