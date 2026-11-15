import type { GraphPayload } from "./contracts";
import { LAYER_LABEL, sortKinds } from "./graph";

/**
 * A zoomable map of the source graph that stays readable at any size.
 *
 * Tied outlets are arranged in a tree: connected group of ties → cluster (`clusters`) → operator → outlet.
 * Every node has at most `FANOUT` children: the smallest siblings are folded into "smaller groups"
 * nodes, recursively, so the tree is about log_FANOUT(n) levels deep whatever the graph's size.
 *
 * The map draws a cut through the tree: a node opens when its circle is on screen and larger than
 * `EXPAND_PX`, otherwise it is drawn as one circle standing for all the sites inside it. The number
 * of circles on screen depends on the zoom, not on the size of the graph. Children are laid out only
 * when their parent first opens, inside the parent's circle, so opening a node never moves the rest.
 * Ties are drawn between the circles that stand for their two outlets in the current cut.
 *
 * Colour: every node carries the colour of its group (`hue`): the cluster it is in, or else the
 * connected group of ties. The `GROUP_COLORS` groups with the most sites get their own colour, the
 * others are drawn grey, so one colour always means one group.
 */

const FANOUT = 64;
/** How many of the largest siblings stay visible when a level is folded. */
const KEEP = 40;
/** A circle opens when its on-screen radius passes this many pixels. */
const EXPAND_PX = 90;
const ROOT_RADIUS = 1000;
/** Gap between sibling circles, in units of one outlet's radius, plus a share of the smaller circle. */
const GAP = 1.4;
const GAP_SHARE = 0.35;
/** The top level is laid out this many times wider than tall, to fill a landscape view. */
const ROOT_ASPECT = 1.6;
/** Share of the parent's radius its children may fill. */
const FILL = 0.8;
/** Groups that get their own colour (`--group-1` to `--group-N` in index.css). */
export const GROUP_COLORS = 10;
const ITERATIONS = 200;

export type MapNodeKind = "root" | "component" | "cluster" | "operator" | "bucket" | "outlet";

export interface MapNode {
  id: number;
  kind: MapNodeKind;
  label: string;
  detail: string;
  /** The outlet's domain; null for every group. */
  domain: string | null;
  /** The cluster id for a `cluster` node, as numbered in the lists. */
  cluster: number | null;
  children: MapNode[];
  parent: MapNode | null;
  /** Position among the parent's children. */
  index: number;
  depth: number;
  /** Outlets below this node (1 for an outlet). */
  leaves: number;
  /** Ties of an outlet (0 for a group): among outlets, the most tied stay visible when a level is folded. */
  ties: number;
  /** World position and radius, set when the parent's children are laid out. */
  x: number;
  y: number;
  r: number;
  placed: boolean;
  /** Summed tie strength between two children, keyed `i * 65536 + j` with i < j. */
  links: Map<number, number>;
  /** Id of the group node whose colour this node takes, or -1. */
  group: number;
  /** 0 to GROUP_COLORS - 1, or -1 for grey. */
  hue: number;
}

export interface MapTie {
  readonly a: number;
  readonly b: number;
  readonly strength: number;
  readonly coordination: number;
}

export interface GraphMap {
  readonly root: MapNode;
  /** Every node, by id. */
  readonly nodes: readonly MapNode[];
  readonly leafOf: ReadonlyMap<string, MapNode>;
  /** Root-to-leaf node ids for each outlet, by leaf id. */
  readonly paths: readonly Int32Array[];
  /** Ties between outlets, by leaf id. */
  readonly ties: readonly MapTie[];
  /** Outlets with no tie at all: not drawn. */
  readonly untied: number;
  /** The groups with their own colour, by hue. */
  readonly colored: readonly MapNode[];
}

function makeNode(kind: MapNodeKind, label: string, detail: string, children: MapNode[]): MapNode {
  return {
    id: -1,
    kind,
    label,
    detail,
    domain: null,
    cluster: null,
    children,
    parent: null,
    index: 0,
    depth: 0,
    leaves: 0,
    ties: 0,
    x: 0,
    y: 0,
    r: 0,
    placed: false,
    links: new Map(),
    group: -1,
    hue: -1,
  };
}

function sites(n: number): string {
  return n === 1 ? "1 site" : `${n} sites`;
}

/** At most FANOUT children: keep the largest, fold the rest into "smaller groups" nodes. */
function capFanout(children: MapNode[]): MapNode[] {
  // Largest first, then the most tied; ties broken by label so the map is the same on every load.
  const sorted = [...children].sort(
    (x, y) => y.leaves - x.leaves || y.ties - x.ties || (x.label < y.label ? -1 : x.label > y.label ? 1 : 0),
  );
  if (sorted.length <= FANOUT) return sorted;
  const keep = sorted.slice(0, KEEP);
  let rest = sorted.slice(KEEP);
  while (rest.length > FANOUT - KEEP) {
    const folded: MapNode[] = [];
    for (let i = 0; i < rest.length; i += FANOUT) {
      const chunk = rest.slice(i, i + FANOUT);
      const leaves = chunk.reduce((sum, n) => sum + n.leaves, 0);
      const onlyOutlets = chunk.every((n) => n.kind === "outlet");
      const fewest = Math.min(...chunk.map((n) => n.ties));
      const most = Math.max(...chunk.map((n) => n.ties));
      const range = fewest === most ? `${fewest}` : `${fewest} to ${most}`;
      const node = makeNode(
        "bucket",
        onlyOutlets ? `${chunk.length} more sites` : `${chunk.length} smaller groups`,
        onlyOutlets
          ? `${sites(leaves)} with ${range} ${most === 1 ? "tie" : "ties"} each`
          : `${sites(leaves)} in ${chunk.length} groups`,
        chunk,
      );
      node.leaves = leaves;
      folded.push(node);
    }
    rest = folded;
  }
  return keep.concat(rest);
}

/** Outlets of one parent, with outlets of a shared operator under one node (unless that is all of them). */
function operatorGroups(domains: readonly string[], leafOf: ReadonlyMap<string, MapNode>, operatorOf: (d: string) => string): MapNode[] {
  const byOperator = new Map<string, string[]>();
  for (const domain of domains) {
    const operator = operatorOf(domain);
    const list = byOperator.get(operator) ?? [];
    list.push(domain);
    byOperator.set(operator, list);
  }
  if (byOperator.size === 1) return domains.map((d) => leafOf.get(d)!);
  const out: MapNode[] = [];
  for (const [operator, members] of byOperator) {
    if (members.length === 1) {
      out.push(leafOf.get(members[0])!);
      continue;
    }
    const node = makeNode("operator", operator, `${sites(members.length)} of one operator`, capFanout(members.map((d) => leafOf.get(d)!)));
    node.leaves = members.length;
    out.push(node);
  }
  return out;
}

export function buildGraphMap(graph: GraphPayload): GraphMap {
  const outlets = new Map(graph.outlets.map((o) => [o.domain, o]));
  const edges = graph.edges.filter((e) => outlets.has(e.a) && outlets.has(e.b) && e.a !== e.b);
  const operatorOf = (d: string) => outlets.get(d)?.operator ?? d;

  // Connected groups over every tie (union-find).
  const parentOf = new Map<string, string>();
  const find = (d: string): string => {
    let x = d;
    while (parentOf.get(x) !== x) {
      const up = parentOf.get(parentOf.get(x)!)!;
      parentOf.set(x, up);
      x = up;
    }
    return x;
  };
  const degree = new Map<string, number>();
  for (const e of edges) {
    for (const d of [e.a, e.b]) {
      if (!parentOf.has(d)) parentOf.set(d, d);
      degree.set(d, (degree.get(d) ?? 0) + 1);
    }
    const ra = find(e.a);
    const rb = find(e.b);
    if (ra !== rb) parentOf.set(ra, rb);
  }
  const components = new Map<string, string[]>();
  for (const d of [...parentOf.keys()].sort()) {
    const r = find(d);
    const list = components.get(r) ?? [];
    list.push(d);
    components.set(r, list);
  }

  const leafOf = new Map<string, MapNode>();
  for (const d of parentOf.keys()) {
    const leaf = makeNode("outlet", d, operatorOf(d), []);
    leaf.domain = d;
    leaf.leaves = 1;
    leaf.ties = degree.get(d) ?? 0;
    leafOf.set(d, leaf);
  }

  const clusterById = new Map(graph.clusters.map((c) => [c.id, c]));
  const clusterNode = (id: number, domains: readonly string[]): MapNode => {
    const joined = clusterById.get(id)?.joined_by ?? [];
    const detail = joined.length
      ? `${sites(domains.length)}, joined by ${sortKinds(joined)
          .map((k) => LAYER_LABEL[k].charAt(0).toLowerCase() + LAYER_LABEL[k].slice(1))
          .join(", ")}`
      : sites(domains.length);
    const node = makeNode("cluster", `Group #${id}`, detail, capFanout(operatorGroups(domains, leafOf, operatorOf)));
    node.cluster = id;
    node.leaves = domains.length;
    return node;
  };

  const top: MapNode[] = [];
  for (const domains of components.values()) {
    const byCluster = new Map<number, string[]>();
    const loose: string[] = [];
    for (const d of domains) {
      const c = outlets.get(d)?.cluster ?? null;
      if (c === null) {
        loose.push(d);
      } else {
        const list = byCluster.get(c) ?? [];
        list.push(d);
        byCluster.set(c, list);
      }
    }
    if (byCluster.size === 1 && loose.length === 0) {
      const [[id, members]] = [...byCluster];
      top.push(clusterNode(id, members));
      continue;
    }
    const children = [...byCluster].map(([id, members]) => clusterNode(id, members)).concat(operatorGroups(loose, leafOf, operatorOf));
    if (children.length === 1) {
      top.push(children[0]);
      continue;
    }
    const hub = domains.reduce((best, d) => ((degree.get(d) ?? 0) > (degree.get(best) ?? 0) ? d : best), domains[0]);
    const node = makeNode(
      "component",
      `${hub} and ${domains.length - 1} more`,
      byCluster.size
        ? `${sites(domains.length)} tied together, including ${byCluster.size === 1 ? "1 group" : `${byCluster.size} groups`}`
        : `${sites(domains.length)} tied together`,
      capFanout(children),
    );
    node.leaves = domains.length;
    top.push(node);
  }

  const root = makeNode("root", "All tied sites", sites(leafOf.size), capFanout(top));

  // Ids, parents, depths, leaf counts, root-to-leaf paths.
  const nodes: MapNode[] = [];
  const paths: Int32Array[] = [];
  const stack: number[] = [];
  const visit = (node: MapNode, parent: MapNode | null, index: number, depth: number): number => {
    node.id = nodes.length;
    node.parent = parent;
    node.index = index;
    node.depth = depth;
    nodes.push(node);
    stack.push(node.id);
    if (node.kind === "outlet") {
      node.leaves = 1;
      paths[node.id] = Int32Array.from(stack);
    } else {
      node.leaves = node.children.reduce((sum, child, i) => sum + visit(child, node, i, depth + 1), 0);
    }
    stack.pop();
    return node.leaves;
  };
  visit(root, null, 0, 0);
  const colored = assignColors(nodes);

  // Tie strength between the two children of the lowest common ancestor, for the layout.
  const ties: MapTie[] = [];
  for (const e of edges) {
    const la = leafOf.get(e.a)!;
    const lb = leafOf.get(e.b)!;
    ties.push({ a: la.id, b: lb.id, strength: e.strength, coordination: e.coordination });
    let x = la;
    let y = lb;
    while (x.depth > y.depth) x = x.parent!;
    while (y.depth > x.depth) y = y.parent!;
    while (x.parent !== y.parent) {
      x = x.parent!;
      y = y.parent!;
    }
    const i = Math.min(x.index, y.index);
    const j = Math.max(x.index, y.index);
    const links = x.parent!.links;
    links.set(i * 65536 + j, (links.get(i * 65536 + j) ?? 0) + e.strength);
  }

  root.r = ROOT_RADIUS;
  root.placed = true;
  placeChildren(root);
  return { root, nodes, leafOf, paths, ties, untied: graph.outlets.length - leafOf.size, colored };
}

/**
 * Group of every node (parents come before children in `nodes`): a cluster starts its own group,
 * a node right under the root (or under a root-level "smaller groups" node) starts one, and every
 * other node takes its parent's. The groups holding the most sites directly get a colour.
 */
function assignColors(nodes: readonly MapNode[]): MapNode[] {
  const own = new Map<number, number>();
  for (const node of nodes) {
    const p = node.parent;
    if (!p) continue;
    if (node.kind === "bucket") {
      node.group = p.group;
      continue;
    }
    node.group = node.kind === "cluster" || p.group < 0 ? node.id : p.group;
    if (node.kind === "outlet") own.set(node.group, (own.get(node.group) ?? 0) + 1);
  }
  const ranked = [...own].sort((x, y) => y[1] - x[1] || x[0] - y[0]).slice(0, GROUP_COLORS).map(([id]) => nodes[id]);
  const hueOf = new Map(ranked.map((n, i) => [n.id, i]));
  for (const node of nodes) node.hue = hueOf.get(node.group) ?? -1;
  return ranked;
}

/** Lay out every ancestor's children so the node has a position (for jumping to it from a list). */
export function reveal(node: MapNode): void {
  const chain: MapNode[] = [];
  for (let n = node.parent; n; n = n.parent) chain.push(n);
  for (let i = chain.length - 1; i >= 0; i--) placeChildren(chain[i]);
}

/**
 * Lay out a node's children inside its circle: a deterministic spiral start, springs along ties,
 * a pull to the centre and no overlap; then scaled to fit. Children of at most FANOUT nodes, once.
 */
export function placeChildren(node: MapNode): void {
  const kids = node.children;
  const n = kids.length;
  if (n === 0 || kids[0].placed) return;
  // The top level is drawn on its own, not inside a circle: spread it wide.
  const pullX = node.kind === "root" ? 0.02 / (ROOT_ASPECT * ROOT_ASPECT) : 0.02;
  const rad = kids.map((k) => Math.sqrt(k.leaves));
  const px = new Float64Array(n);
  const py = new Float64Array(n);
  let area = 0;
  for (let i = 0; i < n; i++) {
    area += rad[i] * rad[i];
    const d = i === 0 ? 0 : Math.sqrt(area) * 1.6;
    px[i] = d * Math.cos(i * 2.399963) * (node.kind === "root" ? ROOT_ASPECT : 1);
    py[i] = d * Math.sin(i * 2.399963);
  }
  const gap = (i: number, j: number) => GAP + GAP_SHARE * Math.min(rad[i], rad[j]);
  const links = [...node.links].map(([key, w]) => [Math.floor(key / 65536), key % 65536, w] as const);

  /** One pass pushing overlapping pairs apart; returns how many pairs overlapped. */
  const collide = (strength: number): number => {
    let overlaps = 0;
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const min = rad[i] + rad[j] + gap(i, j);
        let dx = px[j] - px[i];
        let dy = py[j] - py[i];
        let d2 = dx * dx + dy * dy;
        if (d2 >= min * min * 0.999) continue;
        overlaps += 1;
        if (d2 === 0) {
          dx = 1e-3 * (j - i);
          dy = 1e-3;
          d2 = dx * dx + dy * dy;
        }
        const d = Math.sqrt(d2);
        const push = ((min - d) / d) * strength;
        const ai = rad[i] * rad[i];
        const aj = rad[j] * rad[j];
        const wi = aj / (ai + aj);
        const wj = ai / (ai + aj);
        px[i] -= dx * push * wi;
        py[i] -= dy * push * wi;
        px[j] += dx * push * wj;
        py[j] += dy * push * wj;
      }
    }
    return overlaps;
  };

  for (let it = 0; it < ITERATIONS; it++) {
    const alpha = 1 - it / ITERATIONS;
    for (const [i, j, w] of links) {
      const dx = px[j] - px[i];
      const dy = py[j] - py[i];
      const dist = Math.hypot(dx, dy) || 1e-6;
      const f = ((dist - (rad[i] + rad[j] + gap(i, j))) / dist) * 0.08 * Math.min(1, w) * alpha;
      px[i] += dx * f;
      py[i] += dy * f;
      px[j] -= dx * f;
      py[j] -= dy * f;
    }
    for (let i = 0; i < n; i++) {
      px[i] *= 1 - pullX * alpha;
      py[i] *= 1 - 0.02 * alpha;
    }
    collide(0.5);
  }
  for (let it = 0; it < 200 && collide(1) > 0; it++);

  // Centre on the bounding box, then fit the enclosing circle inside the parent.
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (let i = 0; i < n; i++) {
    minX = Math.min(minX, px[i] - rad[i]);
    maxX = Math.max(maxX, px[i] + rad[i]);
    minY = Math.min(minY, py[i] - rad[i]);
    maxY = Math.max(maxY, py[i] + rad[i]);
  }
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  let enclosing = 0;
  for (let i = 0; i < n; i++) enclosing = Math.max(enclosing, Math.hypot(px[i] - cx, py[i] - cy) + rad[i]);
  const scale = (node.r * (n === 1 ? 0.6 : FILL)) / enclosing;
  for (let i = 0; i < n; i++) {
    kids[i].x = node.x + (px[i] - cx) * scale;
    kids[i].y = node.y + (py[i] - cy) * scale;
    kids[i].r = rad[i] * scale;
    kids[i].placed = true;
  }
}

export interface View {
  /** Pixels per world unit, and the screen position of the world origin. */
  k: number;
  tx: number;
  ty: number;
  width: number;
  height: number;
}

export interface Cut {
  /** Open nodes, parents before children (the root first). */
  readonly open: readonly MapNode[];
  /** Closed nodes and outlets standing for everything below them, also off screen. */
  readonly shown: readonly MapNode[];
  readonly isOpen: Uint8Array;
  /** Identifies the cut: the ties only need regrouping when it changes. */
  readonly key: string;
}

export function onScreen(node: MapNode, view: View, margin = 0): boolean {
  const sx = node.x * view.k + view.tx;
  const sy = node.y * view.k + view.ty;
  const sr = node.r * view.k + margin;
  return sx + sr >= 0 && sx - sr <= view.width && sy + sr >= 0 && sy - sr <= view.height;
}

export function computeCut(map: GraphMap, view: View): Cut {
  const isOpen = new Uint8Array(map.nodes.length);
  const open: MapNode[] = [];
  const shown: MapNode[] = [];
  const walk = (node: MapNode) => {
    const opens =
      node.children.length > 0 && (node === map.root || (node.r * view.k > EXPAND_PX && onScreen(node, view)));
    if (!opens) {
      shown.push(node);
      return;
    }
    placeChildren(node);
    isOpen[node.id] = 1;
    open.push(node);
    for (const child of node.children) walk(child);
  };
  walk(map.root);
  return { open, shown, isOpen, key: open.map((n) => n.id).join(",") };
}

export interface MapLink {
  readonly a: MapNode;
  readonly b: MapNode;
  /** Ties between outlets behind this line. */
  readonly ties: number;
  readonly coordination: number;
  readonly strength: number;
}

/** The ties between the nodes of a cut: each outlet is represented by its first closed ancestor. */
export function linksOf(map: GraphMap, cut: Cut): MapLink[] {
  // First closed node on the outlet's path from the root, cached per outlet.
  const cache = new Int32Array(map.nodes.length).fill(-1);
  const rep = (leaf: number): number => {
    if (cache[leaf] >= 0) return cache[leaf];
    const path = map.paths[leaf];
    let found = leaf;
    for (let i = 0; i < path.length; i++) {
      if (!cut.isOpen[path[i]]) {
        found = path[i];
        break;
      }
    }
    cache[leaf] = found;
    return found;
  };
  const size = map.nodes.length;
  const grouped = new Map<number, { a: number; b: number; ties: number; coordination: number; strength: number }>();
  for (const tie of map.ties) {
    const ra = rep(tie.a);
    const rb = rep(tie.b);
    if (ra === rb) continue;
    const a = Math.min(ra, rb);
    const b = Math.max(ra, rb);
    const key = a * size + b;
    const link = grouped.get(key);
    if (link) {
      link.ties += 1;
      link.coordination = Math.max(link.coordination, tie.coordination);
      link.strength = Math.max(link.strength, tie.strength);
    } else {
      grouped.set(key, { a, b, ties: 1, coordination: tie.coordination, strength: tie.strength });
    }
  }
  return [...grouped.values()].map((l) => ({ ...l, a: map.nodes[l.a], b: map.nodes[l.b] }));
}

/** Ids of the outlets whose domain or operator contains the text, and of every node above them. */
export function matching(map: GraphMap, needle: string): Set<number> {
  const out = new Set<number>();
  if (!needle) return out;
  for (const [domain, leaf] of map.leafOf) {
    if (!domain.includes(needle) && !leaf.detail.includes(needle)) continue;
    for (const id of map.paths[leaf.id]) out.add(id);
  }
  return out;
}

/** The view that shows a node filling most of the viewport; for the root, the box around its children. */
export function viewFor(node: MapNode, width: number, height: number): View {
  if (node.kind === "root" && node.children.length > 0 && node.children[0].placed) {
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const c of node.children) {
      minX = Math.min(minX, c.x - c.r);
      maxX = Math.max(maxX, c.x + c.r);
      minY = Math.min(minY, c.y - c.r);
      maxY = Math.max(maxY, c.y + c.r);
    }
    // Room around the edge for the labels under the circles.
    const k = Math.min((width - 80) / (maxX - minX), (height - 90) / (maxY - minY));
    return { k, tx: width / 2 - ((minX + maxX) / 2) * k, ty: height / 2 - ((minY + maxY) / 2) * k, width, height };
  }
  const k = (Math.min(width, height) * 0.46) / node.r;
  return { k, tx: width / 2 - node.x * k, ty: height / 2 - node.y * k, width, height };
}
