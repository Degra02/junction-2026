import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { Maximize2, Minus, Plus } from "lucide-react";
import type { GraphPayload } from "../../lib/contracts";
import type { GraphIndex } from "../../lib/graph";
import {
  buildGraphMap,
  computeCut,
  linksOf,
  matching,
  onScreen,
  viewFor,
  type Cut,
  type MapLink,
  type MapNode,
  type View,
} from "../../lib/graphMap";
import { buttonClass } from "../../lib/ui";

export interface GraphMapViewProps {
  readonly graph: GraphPayload;
  readonly index: GraphIndex;
  /** Lower-case search text from the page: matching sites and the groups holding them get a ring. */
  readonly needle: string;
  readonly onOpenOutlet: (domain: string) => void;
}

/** Smallest pointer target around a dot, in pixels. */
const MIN_HIT_PX = 7;
const ANIMATION_MS = 450;
/** Zoom range relative to the view that fits everything. */
const MIN_ZOOM = 0.4;
const MAX_ZOOM = 1e6;

/**
 * A node's radius on screen. A site is a dot of at most 9 px whatever the zoom: its circle in the
 * layout only reserves room, and a growing disc would read as a bigger or more important site.
 */
function screenRadius(node: MapNode, k: number): number {
  return node.kind === "outlet" ? Math.min(Math.max(node.r * k, 2.5), 9) : Math.max(node.r * k, 3);
}

interface Palette {
  readonly fg: string;
  readonly secondary: string;
  readonly muted: string;
  readonly border: string;
  readonly subtle: string;
  readonly accent: string;
  readonly accentSoft: string;
  readonly indigo: string;
  readonly caution: string;
  readonly surface: string;
  readonly sans: string;
}

interface Scene {
  readonly cut: Cut;
  readonly links: readonly MapLink[];
}

interface Hover {
  readonly node: MapNode;
  readonly x: number;
  readonly y: number;
  /** Open the tooltip to the left of the pointer, near the right edge. */
  readonly flip: boolean;
}

/** The theme tokens, read at draw time so a light/dark switch repaints with the right colours. */
function palette(el: Element): Palette {
  const style = getComputedStyle(el);
  const token = (name: string) => style.getPropertyValue(name).trim();
  return {
    fg: token("--fg-primary"),
    secondary: token("--fg-secondary"),
    muted: token("--fg-muted"),
    border: token("--border-strong"),
    subtle: token("--bg-subtle"),
    accent: token("--accent"),
    accentSoft: token("--accent-soft"),
    indigo: token("--indigo"),
    caution: token("--caution"),
    surface: token("--bg-surface"),
    sans: token("--font-sans") || "sans-serif",
  };
}

/** The text, shortened with an ellipsis to fit the width. */
function fitText(ctx: CanvasRenderingContext2D, text: string, width: number): string {
  if (ctx.measureText(text).width <= width) return text;
  let end = text.length;
  while (end > 1 && ctx.measureText(`${text.slice(0, end)}…`).width > width) end -= 1;
  return `${text.slice(0, end)}…`;
}

interface Label {
  readonly text: string;
  readonly x: number;
  readonly y: number;
  readonly align: CanvasTextAlign;
  readonly font: string;
  readonly color: string;
  /** Higher first: a label that would overlap an already placed one is dropped. */
  readonly priority: number;
}

function paint(
  ctx: CanvasRenderingContext2D,
  view: View,
  colors: Palette,
  scene: Scene,
  matches: ReadonlySet<number>,
  hovered: MapNode | null,
) {
  const { k, tx, ty, width, height } = view;
  const labels: Label[] = [];
  const small = `11px ${colors.sans}`;

  // Open groups: a faint disc with its name along the top.
  for (const node of scene.cut.open) {
    if (node.kind === "root" || !onScreen(node, view)) continue;
    const x = node.x * k + tx;
    const y = node.y * k + ty;
    const r = node.r * k;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.globalAlpha = 0.55;
    ctx.fillStyle = colors.subtle;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.lineWidth = matches.has(node.id) ? 2 : 1;
    ctx.strokeStyle = matches.has(node.id) ? colors.caution : colors.border;
    ctx.stroke();
    const priority = (node === hovered ? 1e9 : 1e5) + (matches.has(node.id) ? 1e6 : 0) + node.leaves;
    const font = `600 12px ${colors.sans}`;
    ctx.font = font;
    const text = fitText(ctx, node.label, Math.max(r * 1.3, 140));
    labels.push({ text, x, y: y - r + 18, align: "center", font, color: colors.secondary, priority });
    if (r > 150) {
      ctx.font = small;
      const detail = fitText(ctx, node.detail, r * 1.5);
      labels.push({ text: detail, x, y: y - r + 33, align: "center", font: small, color: colors.muted, priority: priority - 1 });
    }
  }

  // Ties, grouped between the circles that stand for their outlets.
  for (const link of scene.links) {
    const ax = link.a.x * k + tx;
    const ay = link.a.y * k + ty;
    const bx = link.b.x * k + tx;
    const by = link.b.y * k + ty;
    if (Math.max(ax, bx) < 0 || Math.min(ax, bx) > width || Math.max(ay, by) < 0 || Math.min(ay, by) > height) continue;
    const ar = screenRadius(link.a, k);
    const br = screenRadius(link.b, k);
    const dx = bx - ax;
    const dy = by - ay;
    const d = Math.hypot(dx, dy);
    if (d <= ar + br) continue;
    const touches = hovered !== null && (link.a === hovered || link.b === hovered);
    ctx.globalAlpha = hovered === null ? 0.75 : touches ? 1 : 0.15;
    ctx.strokeStyle = link.coordination >= 0.5 ? colors.accent : link.coordination > 0 ? colors.indigo : colors.muted;
    ctx.setLineDash(link.coordination > 0 ? [] : [4, 4]);
    ctx.lineWidth = Math.min(1 + Math.log2(link.ties), 5) + (touches ? 0.75 : 0);
    ctx.beginPath();
    ctx.moveTo(ax + (dx / d) * ar, ay + (dy / d) * ar);
    ctx.lineTo(bx - (dx / d) * br, by - (dy / d) * br);
    ctx.stroke();
  }
  ctx.setLineDash([]);
  ctx.globalAlpha = 1;

  // Closed groups (one disc with its count) and single sites (a dot with its domain).
  for (const node of scene.cut.shown) {
    if (!onScreen(node, view, 4)) continue;
    const x = node.x * k + tx;
    const y = node.y * k + ty;
    const isHovered = node === hovered;
    const priority = (isHovered ? 1e9 : 0) + (matches.has(node.id) ? 1e6 : 0);
    if (node.kind === "outlet") {
      const r = screenRadius(node, k);
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = isHovered ? colors.fg : colors.secondary;
      ctx.fill();
      if (matches.has(node.id)) {
        ctx.beginPath();
        ctx.arc(x, y, r + 3, 0, Math.PI * 2);
        ctx.lineWidth = 2;
        ctx.strokeStyle = colors.caution;
        ctx.stroke();
      }
      if (node.r * k >= 5 || priority > 0) {
        labels.push({ text: node.label, x: x + r + 4, y: y + 4, align: "left", font: small, color: colors.fg, priority: priority + 10 + node.ties });
      }
      continue;
    }
    const r = screenRadius(node, k);
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = colors.accentSoft;
    ctx.fill();
    ctx.lineWidth = matches.has(node.id) ? 2.5 : isHovered ? 2 : 1.25;
    ctx.strokeStyle = matches.has(node.id) ? colors.caution : colors.accent;
    ctx.stroke();
    if (r >= 10) {
      const size = Math.round(Math.min(15, Math.max(9, r * 0.55)));
      ctx.textAlign = "center";
      ctx.fillStyle = colors.accent;
      ctx.font = `600 ${size}px ${colors.sans}`;
      ctx.fillText(String(node.leaves), x, y + size * 0.36);
    }
    if (r >= 14 || priority > 0) {
      ctx.font = small;
      const text = fitText(ctx, node.label, Math.max(r * 2.4, 120));
      labels.push({ text, x, y: y + r + 14, align: "center", font: small, color: colors.secondary, priority: priority + 1e3 + node.leaves });
    }
  }

  // Labels last, most important first, skipping any that would overlap one already drawn.
  labels.sort((a, b) => b.priority - a.priority);
  const placed: { left: number; right: number; top: number; bottom: number }[] = [];
  ctx.lineJoin = "round";
  for (const label of labels) {
    ctx.font = label.font;
    const w = ctx.measureText(label.text).width;
    const left = label.align === "center" ? label.x - w / 2 : label.x;
    const box = { left: left - 2, right: left + w + 2, top: label.y - 12, bottom: label.y + 4 };
    if (box.right < 0 || box.left > width || box.bottom < 0 || box.top > height) continue;
    if (placed.some((p) => box.left < p.right && box.right > p.left && box.top < p.bottom && box.bottom > p.top)) continue;
    placed.push(box);
    ctx.textAlign = label.align;
    ctx.lineWidth = 3;
    ctx.strokeStyle = colors.surface;
    ctx.strokeText(label.text, label.x, label.y);
    ctx.fillStyle = label.color;
    ctx.fillText(label.text, label.x, label.y);
  }
}

/**
 * The source graph drawn on a canvas, with groups that open as you zoom in (`lib/graphMap.ts`).
 * Position, size and colour say nothing about a site: a disc's size is how many sites it holds.
 */
export default function GraphMapView({ graph, index, needle, onOpenOutlet }: Readonly<GraphMapViewProps>) {
  const map = useMemo(() => buildGraphMap(graph), [graph]);
  const matches = useMemo(() => matching(map, needle), [map, needle]);
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const view = useRef<View>({ k: 1, tx: 0, ty: 0, width: 0, height: 0 });
  const scene = useRef<Scene | null>(null);
  const hovered = useRef<MapNode | null>(null);
  const [hover, setHover] = useState<Hover | null>(null);
  const frame = useRef(0);
  const animation = useRef(0);
  const draw = useRef<() => void>(() => undefined);
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const moved = useRef(0);

  const schedule = useCallback(() => {
    if (frame.current) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = 0;
      draw.current();
    });
  }, []);

  useEffect(() => {
    scene.current = null;
    draw.current = () => {
      const canvas = canvasRef.current;
      const ctx = canvas?.getContext("2d");
      const v = view.current;
      if (!canvas || !ctx || v.width === 0) return;
      const dpr = window.devicePixelRatio || 1;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, v.width, v.height);
      const cut = computeCut(map, v);
      // Regrouping the ties walks every tie: only when the set of open groups changes.
      const links = scene.current?.cut.key === cut.key ? scene.current.links : linksOf(map, cut);
      scene.current = { cut, links };
      paint(ctx, v, palette(canvas), scene.current, matches, hovered.current);
    };
    schedule();
  }, [map, matches, schedule]);

  // Canvas size follows its box; the first size fits the whole graph.
  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return;
    const resize = () => {
      const width = wrap.clientWidth;
      const height = wrap.clientHeight;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      const v = view.current;
      if (v.width === 0) {
        view.current = viewFor(map.root, width, height);
      } else {
        v.tx += (width - v.width) / 2;
        v.ty += (height - v.height) / 2;
        v.width = width;
        v.height = height;
      }
      draw.current();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(wrap);
    const theme = new MutationObserver(schedule);
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => {
      observer.disconnect();
      theme.disconnect();
      cancelAnimationFrame(frame.current);
      cancelAnimationFrame(animation.current);
      frame.current = 0;
    };
  }, [map, schedule]);

  const zoomAt = useCallback(
    (factor: number, x: number, y: number) => {
      cancelAnimationFrame(animation.current);
      const v = view.current;
      const fit = viewFor(map.root, v.width, v.height).k;
      const k = Math.min(fit * MAX_ZOOM, Math.max(fit * MIN_ZOOM, v.k * factor));
      v.tx = x - (x - v.tx) * (k / v.k);
      v.ty = y - (y - v.ty) * (k / v.k);
      v.k = k;
      schedule();
    },
    [map, schedule],
  );

  /** Glide to show a node: zoom in log space, move the centre with an ease-out. */
  const glideTo = useCallback(
    (node: MapNode) => {
      cancelAnimationFrame(animation.current);
      const from = { ...view.current };
      const to = viewFor(node, from.width, from.height);
      const cx0 = (from.width / 2 - from.tx) / from.k;
      const cy0 = (from.height / 2 - from.ty) / from.k;
      const start = performance.now();
      const step = (now: number) => {
        const t = Math.min(1, (now - start) / ANIMATION_MS);
        const e = 1 - (1 - t) ** 3;
        const k = Math.exp(Math.log(from.k) + (Math.log(to.k) - Math.log(from.k)) * e);
        const cx = cx0 + (node.x - cx0) * e;
        const cy = cy0 + (node.y - cy0) * e;
        const v = view.current;
        v.k = k;
        v.tx = v.width / 2 - cx * k;
        v.ty = v.height / 2 - cy * k;
        draw.current();
        animation.current = t < 1 ? requestAnimationFrame(step) : 0;
      };
      animation.current = requestAnimationFrame(step);
    },
    [],
  );

  const hit = useCallback((x: number, y: number): MapNode | null => {
    const current = scene.current;
    if (!current) return null;
    const { k, tx, ty } = view.current;
    const shown = current.cut.shown;
    for (let i = shown.length - 1; i >= 0; i--) {
      const n = shown[i];
      if (Math.hypot(n.x * k + tx - x, n.y * k + ty - y) <= Math.max(screenRadius(n, k), MIN_HIT_PX)) return n;
    }
    const open = current.cut.open;
    for (let i = open.length - 1; i > 0; i--) {
      const n = open[i];
      if (Math.hypot(n.x * k + tx - x, n.y * k + ty - y) <= n.r * k) return n;
    }
    return null;
  }, []);

  const setHovered = useCallback(
    (node: MapNode | null, x: number, y: number) => {
      if (hovered.current !== node) {
        hovered.current = node;
        schedule();
      }
      setHover(node ? { node, x, y, flip: x > view.current.width - 300 } : null);
    },
    [schedule],
  );

  // The wheel zooms around the pointer; a native listener, because React's is passive.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      zoomAt(Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0015)), e.clientX - rect.left, e.clientY - rect.top);
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  const local = (e: ReactPointerEvent | ReactMouseEvent) => {
    const rect = e.currentTarget.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const onPointerDown = (e: ReactPointerEvent<HTMLCanvasElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    cancelAnimationFrame(animation.current);
    pointers.current.set(e.pointerId, local(e));
    if (pointers.current.size === 1) moved.current = 0;
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLCanvasElement>) => {
    const p = local(e);
    const down = pointers.current;
    const prev = down.get(e.pointerId);
    if (!prev) {
      setHovered(hit(p.x, p.y), p.x, p.y);
      return;
    }
    if (down.size === 1) {
      const v = view.current;
      v.tx += p.x - prev.x;
      v.ty += p.y - prev.y;
      moved.current += Math.abs(p.x - prev.x) + Math.abs(p.y - prev.y);
      down.set(e.pointerId, p);
      if (moved.current > 4) setHovered(null, 0, 0);
      schedule();
      return;
    }
    // Two fingers: zoom by the change of their distance, around their midpoint.
    const [first, second] = [...down.entries()];
    const other = first[0] === e.pointerId ? second[1] : first[1];
    const before = Math.hypot(prev.x - other.x, prev.y - other.y);
    const after = Math.hypot(p.x - other.x, p.y - other.y);
    down.set(e.pointerId, p);
    moved.current += 10;
    if (before > 0) zoomAt(after / before, (p.x + other.x) / 2, (p.y + other.y) / 2);
  };

  const onPointerUp = (e: ReactPointerEvent<HTMLCanvasElement>) => {
    const single = pointers.current.size === 1;
    pointers.current.delete(e.pointerId);
    if (!single || moved.current > 4) return;
    const p = local(e);
    const node = hit(p.x, p.y);
    if (!node) return;
    if (node.domain) onOpenOutlet(node.domain);
    else glideTo(node);
  };

  return (
    <div className="space-y-3">
      <div
        ref={wrapRef}
        className="editorial-card relative h-[min(70vh,640px)] overflow-hidden rounded-xl"
        onPointerLeave={() => pointers.current.size === 0 && setHovered(null, 0, 0)}
      >
        <canvas
          ref={canvasRef}
          role="img"
          aria-label={`Map of ${map.root.leaves} sites that share a trace with another site. The lists below hold the same ties.`}
          className="block touch-none cursor-grab active:cursor-grabbing"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={(e) => pointers.current.delete(e.pointerId)}
          onDoubleClick={(e) => {
            const p = local(e);
            zoomAt(2, p.x, p.y);
          }}
        />
        <div className="absolute right-3 top-3 flex flex-col gap-1.5">
          <button
            type="button"
            aria-label="Zoom in"
            className={buttonClass("secondary", "icon")}
            onClick={() => zoomAt(1.6, view.current.width / 2, view.current.height / 2)}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            aria-label="Zoom out"
            className={buttonClass("secondary", "icon")}
            onClick={() => zoomAt(1 / 1.6, view.current.width / 2, view.current.height / 2)}
          >
            <Minus className="h-4 w-4" aria-hidden="true" />
          </button>
          <button type="button" aria-label="Show everything" className={buttonClass("secondary", "icon")} onClick={() => glideTo(map.root)}>
            <Maximize2 className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        {hover && <Tooltip hover={hover} index={index} />}
      </div>
      <Legend untied={map.untied} searching={needle !== ""} />
    </div>
  );
}

function Tooltip({ hover, index }: Readonly<{ hover: Hover; index: GraphIndex }>) {
  const { node } = hover;
  const outlet = node.domain ? index.outlets.get(node.domain) : undefined;
  const ties = node.domain ? (index.ties.get(node.domain)?.length ?? 0) : 0;
  return (
    <div
      className="pointer-events-none absolute z-10 max-w-[280px] rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-popover)] px-3 py-2 text-[12px] shadow-[var(--shadow-floating)]"
      style={{
        left: hover.flip ? hover.x - 14 : hover.x + 14,
        top: hover.y + 14,
        transform: hover.flip ? "translateX(-100%)" : undefined,
      }}
    >
      {outlet ? (
        <>
          <p className="font-mono-num text-[13px] text-[var(--fg-primary)]">{outlet.domain}</p>
          <p className="text-[var(--fg-secondary)]">
            {ties === 1 ? "1 tie" : `${ties} ties`}
            {outlet.cluster !== null && ` · Group #${outlet.cluster}`}
            {outlet.operator !== outlet.domain && ` · operator ${outlet.operator}`}
          </p>
          <p className="mt-1 text-[var(--fg-muted)]">Click to see the evidence.</p>
        </>
      ) : (
        <>
          <p className="text-[13px] font-medium text-[var(--fg-primary)]">{node.label}</p>
          <p className="text-[var(--fg-secondary)]">{node.detail}</p>
          <p className="mt-1 text-[var(--fg-muted)]">Zoom in or click to look inside.</p>
        </>
      )}
    </div>
  );
}

function Legend({ untied, searching }: Readonly<{ untied: number; searching: boolean }>) {
  const line = (stroke: string, dash?: string) => (
    <svg width="28" height="8" aria-hidden="true" className="shrink-0">
      <line x1="1" y1="4" x2="27" y2="4" stroke={stroke} strokeWidth="2" strokeDasharray={dash} />
    </svg>
  );
  return (
    <div className="space-y-2 text-[12px] text-[var(--fg-secondary)]">
      <ul className="flex flex-wrap gap-x-5 gap-y-1.5">
        <li className="flex items-center gap-2">{line("var(--accent)")} Coordination tie, strength 0.5 or more</li>
        <li className="flex items-center gap-2">{line("var(--indigo)")} Weaker coordination tie</li>
        <li className="flex items-center gap-2">{line("var(--fg-muted)", "4 4")} Link or same operator only: not coordination</li>
        <li className="flex items-center gap-2">
          <svg width="14" height="14" aria-hidden="true" className="shrink-0">
            <circle cx="7" cy="7" r="6" fill="var(--accent-soft)" stroke="var(--accent)" />
          </svg>
          Several sites drawn as one, with their number: zoom in or click to open
        </li>
        {searching && (
          <li className="flex items-center gap-2">
            <svg width="14" height="14" aria-hidden="true" className="shrink-0">
              <circle cx="7" cy="7" r="5.5" fill="none" stroke="var(--caution)" strokeWidth="2" />
            </svg>
            Matches the search, or holds a site that does
          </li>
        )}
      </ul>
      <p className="text-[var(--fg-muted)]">
        A thicker line stands for more ties. Position, size and colour say nothing about a site: a circle's size is how many
        sites it holds. {untied} sites with no tie are not drawn.
      </p>
    </div>
  );
}
