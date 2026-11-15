import type {
  GraphArticlePairEvidence,
  GraphCluster,
  GraphEdge,
  GraphEvidence,
  GraphIdEvidence,
  GraphLayer,
  GraphLayerKind,
  GraphLinkEvidence,
  GraphOutlet,
  GraphPayload,
} from "./contracts";

/** What a layer means, in plain words: a shared trace, never a judgement (D4, graph rule 2). */
export const LAYER_LABEL: Record<GraphLayerKind, string> = {
  analytics_id: "Same analytics ID",
  ad_account: "Same ad account",
  copy: "Copied text",
  translation: "Translated text",
  link: "Link",
  same_operator: "Same operator",
};

export const LAYER_HINT: Record<GraphLayerKind, string> = {
  analytics_id:
    "Both sites load the same Google Analytics or Tag Manager ID, found in the page source.",
  ad_account:
    "Both sites carry the same AdSense publisher ID. Weak on its own: ad resellers reuse these IDs.",
  copy:
    "An article of one site contains most of the other's wording, after quotations, agency copy and boilerplate are removed.",
  translation:
    "Articles in different languages whose headline and lead mean the same, published within a week.",
  link: "The analysed article of one site links to the other. Shown for context; not counted as coordination.",
  same_operator: "Both domains belong to one organisation (same registrable domain or a known owner).",
};

/** Layers that count as coordination (`COORDINATION` in pipeline/graph/build.py). */
export const IS_COORDINATION: Record<GraphLayerKind, boolean> = {
  analytics_id: true,
  ad_account: true,
  copy: true,
  translation: true,
  link: false,
  same_operator: false,
};

/** Display order: the strongest kinds of trace first. */
const LAYER_ORDER: readonly GraphLayerKind[] = [
  "analytics_id",
  "copy",
  "translation",
  "ad_account",
  "same_operator",
  "link",
];

export function sortLayers(layers: readonly GraphLayer[]): GraphLayer[] {
  return [...layers].sort((x, y) => LAYER_ORDER.indexOf(x.kind) - LAYER_ORDER.indexOf(y.kind));
}

export function sortKinds(kinds: readonly GraphLayerKind[]): GraphLayerKind[] {
  return [...kinds].sort((x, y) => LAYER_ORDER.indexOf(x) - LAYER_ORDER.indexOf(y));
}

export function isIdEvidence(e: GraphEvidence): e is GraphIdEvidence {
  return "id" in e;
}

export function isPairEvidence(e: GraphEvidence): e is GraphArticlePairEvidence {
  return "a" in e && "b" in e;
}

export function isLinkEvidence(e: GraphEvidence): e is GraphLinkEvidence {
  return "from" in e && "to" in e;
}

/** Which tracker an ID belongs to, from its prefix. */
export function idKind(id: string): string {
  if (id.startsWith("GTM-")) return "Google Tag Manager";
  if (id.startsWith("G-")) return "Google Analytics 4";
  if (id.startsWith("UA-")) return "Universal Analytics";
  if (/^(ca-)?pub-/.test(id)) return "AdSense publisher";
  return "Tracking ID";
}

/**
 * A tie resting on one shared tag seen on one article, with no other coordination layer and no
 * common operator: the thinnest evidence the graph keeps, shown as such next to the tie.
 */
export function isSingleTagTie(edge: GraphEdge): boolean {
  if (edge.layers.some((l) => l.kind === "same_operator")) return false;
  const coordination = edge.layers.filter((l) => IS_COORDINATION[l.kind]);
  return (
    coordination.length === 1 &&
    (coordination[0].kind === "analytics_id" || coordination[0].kind === "ad_account") &&
    (coordination[0].count ?? 0) <= 1
  );
}

export interface GraphIndex {
  readonly outlets: ReadonlyMap<string, GraphOutlet>;
  /** Domain → its ties, strongest coordination first. */
  readonly ties: ReadonlyMap<string, readonly GraphEdge[]>;
  readonly clusters: ReadonlyMap<number, GraphCluster>;
}

export function indexGraph(graph: GraphPayload): GraphIndex {
  const outlets = new Map(graph.outlets.map((o) => [o.domain, o]));
  const ties = new Map<string, GraphEdge[]>();
  for (const edge of graph.edges) {
    for (const domain of [edge.a, edge.b]) {
      const list = ties.get(domain) ?? [];
      list.push(edge);
      ties.set(domain, list);
    }
  }
  for (const list of ties.values()) {
    list.sort(byWeight);
  }
  const clusters = new Map(graph.clusters.map((c) => [c.id, c]));
  return { outlets, ties, clusters };
}

export function byWeight(x: GraphEdge, y: GraphEdge): number {
  return y.coordination - x.coordination || y.strength - x.strength;
}

/** The ties between outlets of one cluster. */
export function clusterTies(graph: GraphPayload, cluster: GraphCluster): GraphEdge[] {
  const members = new Set(cluster.outlets);
  return graph.edges.filter((e) => members.has(e.a) && members.has(e.b)).sort(byWeight);
}

export function otherEnd(edge: GraphEdge, domain: string): string {
  return edge.a === domain ? edge.b : edge.a;
}

/** Host of an article URL, for a compact link label. */
export function shortUrl(url: string): string {
  try {
    const u = new URL(url);
    const path = u.pathname.length > 42 ? `${u.pathname.slice(0, 40)}…` : u.pathname;
    return `${u.hostname.replace(/^www\./, "")}${path}`;
  } catch {
    return url;
  }
}
