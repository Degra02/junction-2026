import type { ContextItem, DocumentData, Evidence } from "./contracts";
import { SOCIAL_PLATFORMS } from "./labels";

/**
 * Social media posts in `context[]` (`pipeline/retrieve/social.py`): public posts that repeat the
 * document's wording, one per account. `retrieved_by` is the platform, `author` the account
 * (older records: only in the title, "Post by @name on Bluesky"), `published_at` is the exact
 * posting time. Everything here only
 * arranges what retrieve found; nothing is scored in the browser.
 */

export interface SocialPost {
  readonly item: ContextItem;
  readonly platform: string;
  readonly account: string;
  readonly at: number | null;
  /** Character range of `item.text` that repeats the document word for word, if found. */
  readonly shared: readonly [number, number] | null;
  /** Cited by a coordinated evidence item (counted as a copy, or in the timing window). */
  readonly citedAs: readonly string[];
}

export interface Burst {
  readonly count: number;
  readonly spanMs: number;
}

export interface Swarm {
  readonly posts: readonly SocialPost[];
  readonly accounts: number;
  readonly platforms: readonly string[];
  /** First to last post. */
  readonly spanMs: number | null;
  /** Most posts inside any one hour, with the time between the first and last of them. */
  readonly burst: Burst | null;
  /** Timeline bounds: the posts and the analysed item when it has a date. */
  readonly start: number | null;
  readonly end: number | null;
}

const ACCOUNT_RE = /^Post by (.+?) on [^\s]+/;
const MIN_SHARED_WORDS = 4;
const BURST_WINDOW_MS = 60 * 60 * 1000;

export function isSocialPost(item: ContextItem): boolean {
  return item.retrieved_by in SOCIAL_PLATFORMS;
}

function accountOf(item: ContextItem): string {
  if (item.author) return item.author;
  // Records from before `context[].author`: the account is in the title.
  const fromTitle = item.title ? ACCOUNT_RE.exec(item.title)?.[1] : undefined;
  if (fromTitle) return fromTitle;
  try {
    const path = new URL(item.url).pathname.split("/").filter(Boolean);
    // bsky.app/profile/<handle>/post/…, x.com/<handle>/status/…, t.me/<channel>/…
    const handle = path[0] === "profile" ? path[1] : path[0];
    if (handle) return handle.startsWith("@") ? handle : `@${handle}`;
  } catch {
    // Not a URL: fall through.
  }
  return "unknown account";
}

function time(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : t;
}

const norm = (word: string) => word.toLocaleLowerCase().replace(/[\p{P}\p{S}]/gu, "");

/** Words of `text` with their character ranges (UTF-16, for slicing the same JS string). */
function words(text: string): { word: string; start: number; end: number }[] {
  const out: { word: string; start: number; end: number }[] = [];
  for (const m of text.matchAll(/\S+/g)) {
    const word = norm(m[0]);
    if (word) out.push({ word, start: m.index, end: m.index + m[0].length });
  }
  return out;
}

/**
 * The longest run of words the post shares with the document, as a character range of the post.
 * Classic longest-common-substring over words, on one rolling row: posts are short.
 */
export function sharedRun(post: string, documentWords: readonly string[]): readonly [number, number] | null {
  const tokens = words(post);
  if (tokens.length === 0 || documentWords.length === 0) return null;
  let prev = new Uint16Array(documentWords.length + 1);
  let best = 0;
  let bestEnd = -1;
  for (let i = 1; i <= tokens.length; i++) {
    const row = new Uint16Array(documentWords.length + 1);
    const w = tokens[i - 1]?.word;
    for (let j = 1; j <= documentWords.length; j++) {
      if (w === documentWords[j - 1]) {
        const run = (prev[j - 1] ?? 0) + 1;
        row[j] = run;
        if (run > best) {
          best = run;
          bestEnd = i - 1;
        }
      }
    }
    prev = row;
  }
  if (best < MIN_SHARED_WORDS) return null;
  const first = tokens[bestEnd - best + 1];
  const last = tokens[bestEnd];
  return first && last ? [first.start, last.end] : null;
}

function biggestBurst(times: readonly number[]): Burst | null {
  if (times.length < 2) return null;
  let best: Burst = { count: 1, spanMs: 0 };
  let lo = 0;
  for (let hi = 0; hi < times.length; hi++) {
    while ((times[hi] ?? 0) - (times[lo] ?? 0) > BURST_WINDOW_MS) lo++;
    const count = hi - lo + 1;
    const spanMs = (times[hi] ?? 0) - (times[lo] ?? 0);
    if (count > best.count || (count === best.count && spanMs < best.spanMs)) best = { count, spanMs };
  }
  return best.count >= 2 ? best : null;
}

export function buildSwarm(
  context: readonly ContextItem[],
  document: DocumentData | null | undefined,
  evidence: readonly Evidence[],
): Swarm | null {
  const items = context.filter(isSocialPost);
  if (items.length === 0) return null;

  const documentWords = words((document?.paragraphs ?? []).join("\n")).map((t) => t.word);
  const cited = new Map<string, string[]>();
  for (const ev of evidence) {
    if (ev.family !== "text_reuse" && ev.family !== "timing") continue;
    for (const ref of ev.source_refs) {
      if (ref.kind !== "context") continue;
      const list = cited.get(ref.id) ?? [];
      list.push(ev.family);
      cited.set(ref.id, list);
    }
  }

  const posts: SocialPost[] = items
    .map((item) => ({
      item,
      platform: SOCIAL_PLATFORMS[item.retrieved_by] ?? item.retrieved_by,
      account: accountOf(item),
      at: time(item.published_at),
      shared: sharedRun(item.text, documentWords),
      citedAs: cited.get(item.id) ?? [],
    }))
    .sort((a, b) => (a.at ?? Infinity) - (b.at ?? Infinity));

  // Span and burst describe the posts; the timeline also places the analysed item.
  const times = posts.map((p) => p.at).filter((t): t is number => t !== null);
  const documentAt = time(document?.published_at);
  const axis = documentAt === null ? times : [...times, documentAt];
  const first = times[0];
  const last = times[times.length - 1];

  return {
    posts,
    accounts: new Set(posts.map((p) => `${p.platform}:${p.account.toLocaleLowerCase()}`)).size,
    platforms: Array.from(new Set(posts.map((p) => p.platform))),
    spanMs: first !== undefined && last !== undefined && times.length > 1 ? last - first : null,
    burst: biggestBurst(times),
    start: axis.length ? Math.min(...axis) : null,
    end: axis.length ? Math.max(...axis) : null,
  };
}

/** "45 s", "12 min", "2 h 5 min", "3 days". */
export function formatSpan(ms: number): string {
  const minutes = Math.round(ms / 60_000);
  if (ms < 60_000) return `${Math.max(1, Math.round(ms / 1000))} s`;
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return minutes % 60 ? `${hours} h ${minutes % 60} min` : `${hours} h`;
  return `${Math.round(hours / 24)} days`;
}

/** Offset of a post from the analysed item: "+3 min", "−2 h", "same minute". */
export function formatOffset(ms: number): string {
  if (Math.abs(ms) < 60_000) return "same minute";
  return `${ms > 0 ? "+" : "−"}${formatSpan(Math.abs(ms))}`;
}
