import type {
  Analysis,
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
import { cleanDomain } from "./evidence";
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

const HOSTING_SUFFIXES = [
  "blogspot.com",
  "wordpress.com",
  "substack.com",
  "medium.com",
  "ghost.io",
  "wixsite.com",
  "squarespace.com",
  "weebly.com",
  "github.io",
  "pages.dev",
  "netlify.app",
  "vercel.app",
  "livejournal.com",
  "tumblr.com",
] as const;

const SOCIAL_HOST_LIST = [
  "x.com",
  "twitter.com",
  "reddit.com",
  "old.reddit.com",
  "bsky.app",
  "t.me",
  "telegram.me",
  "youtube.com",
  "youtu.be",
  "facebook.com",
  "instagram.com",
  "tiktok.com",
  "threads.net",
  "linkedin.com",
] as const;

const TWO_PART_SUFFIXES: Readonly<Record<string, true>> = {
  "co.uk": true,
  "org.uk": true,
  "gov.uk": true,
  "ac.uk": true,
  "com.au": true,
  "net.au": true,
  "org.au": true,
  "co.nz": true,
  "com.br": true,
  "gob.es": true,
  "gouv.fr": true,
};

const LAYER_PARAMS: Partial<Record<GraphLayerKind, readonly [number, number]>> = {
  analytics_id: [1.0, 0.75],
  ad_account: [1.0, 0.2],
  copy: [2.0, 0.8],
  translation: [2.0, 0.8],
  link: [3.0, 0.3],
};

const ANALYTICS_RE = /^(UA-\d+(-\d+)?|G-[A-Z0-9]+|GTM-[A-Z0-9]+)$/;
const AD_ACCOUNT_RE = /^(?:ca-)?pub-(\d+)$/;
const COUNTING_DIGITS = "01234567890123456789";

function isHostedDomain(domain: string): boolean {
  return HOSTING_SUFFIXES.some((s) => domain === s || domain.endsWith(`.${s}`));
}

function isSocialDomain(domain: string): boolean {
  return SOCIAL_HOST_LIST.some((host) => domain === host || domain.endsWith(`.${host}`));
}

function inferOperator(domain: string): string {
  if (isHostedDomain(domain)) return domain;
  const parts = domain.split(".");
  if (parts.length <= 2) return domain;
  const tail2 = parts.slice(-2).join(".");
  return TWO_PART_SUFFIXES[tail2] ? parts.slice(-3).join(".") : tail2;
}

function classifyTrackingId(value: string): "analytics_id" | "ad_account" | null {
  if (ANALYTICS_RE.test(value)) return "analytics_id";
  const m = AD_ACCOUNT_RE.exec(value);
  if (m) {
    const digits = m[1]!;
    if (COUNTING_DIGITS.includes(digits) || new Set(digits).size === 1) return null;
    return "ad_account";
  }
  return null;
}

function noisyOr(layers: readonly GraphLayer[], coordOnly: boolean): number {
  let miss = 1.0;
  for (const layer of layers) {
    if (coordOnly && !IS_COORDINATION[layer.kind]) continue;
    const params = LAYER_PARAMS[layer.kind];
    if (!params) continue;
    const [tau, q] = params;
    const count = Math.max(1, layer.count ?? 1);
    miss *= 1.0 - q * (1.0 - Math.exp(-count / tau));
  }
  return Math.round((1.0 - miss) * 1000) / 1000;
}

export interface AnalysisSubgraph {
  /** Resolved outlet domain for the analysed item, or null on pasted text / image without URL. */
  readonly focusDomain: string | null;
  /** Ego + cluster subgraph ready for `GraphMapView`. */
  readonly subgraph: GraphPayload;
  readonly index: GraphIndex;
  /** Direct ties incident to `focusDomain` (or all ties in the subgraph when `focusDomain` is null). */
  readonly directTies: readonly GraphEdge[];
  readonly cluster: GraphCluster | null;
}

/**
 * Builds the partial source graph around the analysed website: merges the published `/api/graph`
 * snapshot with non-topic traces from `analysis` itself (shared analytics/ad tags, `text_reuse`
 * copies, same registrable operator, and outbound links — never topic overlap, per graph rule 3).
 */
export function extractAnalysisSubgraph(
  graph: GraphPayload | null,
  analysis: Analysis,
  rawPrimaryDomain: string,
): AnalysisSubgraph {
  const outletsMap = new Map<string, GraphOutlet>();
  if (graph) {
    for (const o of graph.outlets) {
      outletsMap.set(o.domain, o);
    }
  }

  const ensureOutlet = (raw: string | null | undefined, analysed = 0): string => {
    const d = cleanDomain(raw);
    if (!d || isSocialDomain(d)) return "";
    if (!outletsMap.has(d)) {
      const src = analysis.sources.find((s) => cleanDomain(s.domain) === d);
      outletsMap.set(d, {
        domain: d,
        operator: inferOperator(d),
        outlet_type: src?.outlet_type ?? null,
        country: src?.country ?? null,
        known_network: src?.known_network ?? null,
        articles: 1,
        analysed,
        cluster: null,
      });
    }
    return d;
  };

  const docDomain = ensureOutlet(
    analysis.document?.outlet ?? analysis.document?.url ?? rawPrimaryDomain,
    1,
  );
  const contextById = new Map(analysis.context.map((c) => [c.id, c]));
  const contextDomains: string[] = [];
  for (const ctx of analysis.context) {
    const cd = ensureOutlet(ctx.outlet ?? ctx.url, 0);
    if (cd) contextDomains.push(cd);
  }
  for (const src of analysis.sources) {
    ensureOutlet(src.domain, 0);
  }

  // Keyed `a|b` with a < b.
  const edgeMap = new Map<string, Map<GraphLayerKind, { count: number; evidence: GraphEvidence[] }>>();
  const pairKey = (x: string, y: string): [string, string, string] =>
    x < y ? [x, y, `${x}|${y}`] : [y, x, `${y}|${x}`];

  if (graph) {
    for (const e of graph.edges) {
      const [, , key] = pairKey(e.a, e.b);
      const layers = new Map<GraphLayerKind, { count: number; evidence: GraphEvidence[] }>();
      for (const l of e.layers) {
        layers.set(l.kind, { count: l.count ?? 1, evidence: [...(l.evidence ?? [])] });
      }
      edgeMap.set(key, layers);
    }
  }

  const addLiveTie = (x: string, y: string, kind: GraphLayerKind, ev?: GraphEvidence) => {
    if (!x || !y || x === y) return;
    const [, , key] = pairKey(x, y);
    let layers = edgeMap.get(key);
    if (!layers) {
      layers = new Map();
      edgeMap.set(key, layers);
    }
    const existing = layers.get(kind);
    if (!existing) {
      layers.set(kind, { count: 1, evidence: ev ? [ev] : [] });
    } else if (ev && existing.evidence.length < 3) {
      const serialized = JSON.stringify(ev);
      if (!existing.evidence.some((item) => JSON.stringify(item) === serialized)) {
        existing.evidence.push(ev);
      }
    }
  };

  // 1. Live shared tracking IDs across non-hosted outlets in this analysis.
  const idCarriers = new Map<string, Set<string>>();
  if (docDomain && !isHostedDomain(docDomain)) {
    for (const tid of analysis.document?.tracking_ids ?? []) {
      if (!classifyTrackingId(tid)) continue;
      const set = idCarriers.get(tid) ?? new Set();
      set.add(docDomain);
      idCarriers.set(tid, set);
    }
  }
  for (const ctx of analysis.context) {
    const cd = cleanDomain(ctx.outlet ?? ctx.url);
    if (!cd || isSocialDomain(cd) || isHostedDomain(cd)) continue;
    for (const tid of ctx.tracking_ids) {
      if (!classifyTrackingId(tid)) continue;
      const set = idCarriers.get(tid) ?? new Set();
      set.add(cd);
      idCarriers.set(tid, set);
    }
  }
  for (const [tid, domains] of idCarriers) {
    const kind = classifyTrackingId(tid);
    if (!kind || domains.size < 2 || domains.size > 20) continue;
    const list = [...domains];
    for (let i = 0; i < list.length; i++) {
      for (let j = i + 1; j < list.length; j++) {
        addLiveTie(list[i]!, list[j]!, kind, { id: tid });
      }
    }
  }

  // 2. Live copied-passage ties emitted by `signals_coordinated`.
  const docUrl = analysis.document?.url ?? (docDomain ? `https://${docDomain}` : "");
  if (docDomain) {
    for (const ev of analysis.evidence) {
      if (ev.family !== "text_reuse" || ev.signal !== "copied_passages") continue;
      for (const ref of ev.source_refs) {
        if (ref.kind !== "context") continue;
        const ctx = contextById.get(ref.id);
        const cd = ensureOutlet(ctx?.outlet ?? ctx?.url, 0);
        if (!cd || cd === docDomain) continue;
        const [a, b] = docDomain < cd ? [docUrl, ctx?.url ?? `https://${cd}`] : [ctx?.url ?? `https://${cd}`, docUrl];
        addLiveTie(docDomain, cd, "copy", a && b ? { a, b } : undefined);
      }
    }

    // 3. Outbound links from the analysed document to known non-social outlets of another operator.
    const docOp = outletsMap.get(docDomain)?.operator ?? docDomain;
    for (const link of analysis.document?.outbound_links ?? []) {
      const target = cleanDomain(link);
      if (!target || target === docDomain || isSocialDomain(target) || !outletsMap.has(target)) continue;
      if ((outletsMap.get(target)?.operator ?? target) === docOp) continue;
      addLiveTie(docDomain, target, "link", { from: docDomain, to: target });
    }
  }

  // 4. Same-operator ties among outlets present in this analysis.
  const analysisDomains = [...new Set([docDomain, ...contextDomains].filter(Boolean))];
  for (let i = 0; i < analysisDomains.length; i++) {
    for (let j = i + 1; j < analysisDomains.length; j++) {
      const dx = analysisDomains[i]!;
      const dy = analysisDomains[j]!;
      const ox = outletsMap.get(dx)?.operator ?? dx;
      const oy = outletsMap.get(dy)?.operator ?? dy;
      if (ox === oy && !isHostedDomain(dx) && !isHostedDomain(dy)) {
        addLiveTie(dx, dy, "same_operator");
      }
    }
  }

  const allEdges: GraphEdge[] = [];
  for (const [key, layersMap] of edgeMap) {
    const [a, b] = key.split("|") as [string, string];
    if (!outletsMap.has(a) || !outletsMap.has(b)) continue;
    const sameOp = (outletsMap.get(a)!.operator === outletsMap.get(b)!.operator) && !isHostedDomain(a);
    if (sameOp && !layersMap.has("same_operator")) {
      layersMap.set("same_operator", { count: 1, evidence: [] });
    }
    const layers: GraphLayer[] = [...layersMap.entries()].map(([kind, acc]) =>
      kind === "same_operator"
        ? { kind }
        : { kind, count: acc.count, evidence: acc.evidence },
    );
    allEdges.push({
      a,
      b,
      strength: sameOp ? 1.0 : noisyOr(layers, false),
      coordination: noisyOr(layers, true),
      layers: sortLayers(layers),
    });
  }

  // Resolve focus domain (handle regional subdomains like `bologna.repubblica.it` -> `repubblica.it`).
  const cleanedPrimary = cleanDomain(rawPrimaryDomain) || docDomain;
  let focusDomain: string | null = cleanedPrimary || null;
  if (focusDomain && !outletsMap.has(focusDomain)) {
    const parent = [...outletsMap.keys()].find((d) => focusDomain!.endsWith(`.${d}`));
    if (parent) focusDomain = parent;
  }

  // Seed the ego slice: `focusDomain` when known, else the context domains of this analysis.
  const seeds = focusDomain ? [focusDomain] : [...new Set(contextDomains)];
  const keep = new Set<string>(seeds.filter((d) => outletsMap.has(d)));

  for (const seed of [...keep]) {
    const seedOutlet = outletsMap.get(seed);
    const seedOp = seedOutlet?.operator;
    for (const e of allEdges) {
      if (e.a === seed) keep.add(e.b);
      else if (e.b === seed) keep.add(e.a);
    }
    if (seedOutlet?.cluster !== null && seedOutlet?.cluster !== undefined && graph) {
      const cl = graph.clusters.find((c) => c.id === seedOutlet.cluster);
      for (const m of cl?.outlets ?? []) keep.add(m);
    }
    if (seedOp && !isHostedDomain(seed)) {
      for (const o of outletsMap.values()) {
        if (o.operator === seedOp) keep.add(o.domain);
      }
    }
  }

  const subEdges = allEdges.filter((e) => keep.has(e.a) && keep.has(e.b)).sort(byWeight);
  const subClusters: GraphCluster[] = (graph?.clusters ?? [])
    .map((c) => ({
      ...c,
      outlets: c.outlets.filter((d) => keep.has(d)),
    }))
    .filter((c) => c.outlets.length >= 2);

  // If live ties form a coordination/same-operator group not yet in `graph.clusters`, group them locally.
  const clusteredDomains = new Set(subClusters.flatMap((c) => c.outlets));
  const strongLiveEdges = subEdges.filter(
    (e) =>
      (e.coordination >= 0.5 || e.layers.some((l) => l.kind === "same_operator")) &&
      (!clusteredDomains.has(e.a) || !clusteredDomains.has(e.b)),
  );
  if (strongLiveEdges.length > 0) {
    const liveMembers = new Set<string>();
    const joinedKinds = new Set<GraphLayerKind>();
    for (const e of strongLiveEdges) {
      liveMembers.add(e.a);
      liveMembers.add(e.b);
      for (const l of e.layers) {
        if (IS_COORDINATION[l.kind] || l.kind === "same_operator") joinedKinds.add(l.kind);
      }
    }
    const unclustered = [...liveMembers].filter((d) => !clusteredDomains.has(d)).sort();
    if (unclustered.length >= 2) {
      const nextId = Math.max(0, ...(graph?.clusters.map((c) => c.id) ?? [0])) + 1;
      for (const d of unclustered) {
        const o = outletsMap.get(d);
        if (o) outletsMap.set(d, { ...o, cluster: nextId });
      }
      subClusters.push({
        id: nextId,
        outlets: unclustered,
        listed: unclustered.filter((d) => Boolean(outletsMap.get(d)?.known_network)).length,
        joined_by: sortKinds([...joinedKinds]),
      });
    }
  }

  const subOutlets = [...keep]
    .map((d) => outletsMap.get(d))
    .filter((o): o is GraphOutlet => o !== undefined)
    .sort((x, y) => x.domain.localeCompare(y.domain));

  const subgraph: GraphPayload = {
    built_at: graph?.built_at ?? analysis.updated_at,
    counts: {
      analyses: graph?.counts.analyses ?? 1,
      articles: subOutlets.reduce((s, o) => s + o.articles, 0),
      outlets: subOutlets.length,
      edges: subEdges.length,
      clusters: subClusters.length,
    },
    outlets: subOutlets,
    edges: subEdges,
    clusters: subClusters,
  };

  const index = indexGraph(subgraph);
  const directTies = focusDomain ? (index.ties.get(focusDomain) ?? []) : subEdges;
  const focusClusterId = focusDomain ? (index.outlets.get(focusDomain)?.cluster ?? null) : null;
  const cluster = focusClusterId !== null ? (index.clusters.get(focusClusterId) ?? null) : null;

  return { focusDomain, subgraph, index, directTies, cluster };
}
