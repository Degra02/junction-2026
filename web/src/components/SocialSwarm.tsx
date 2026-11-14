import { useMemo } from "react";
import { ExternalLink } from "lucide-react";
import type { ContextItem, DocumentData, Evidence } from "../lib/contracts";
import { formatDateTime } from "../lib/format";
import { buildSwarm, formatOffset, formatSpan, type SocialPost } from "../lib/social";
import { tagClass } from "../lib/ui";
import { cn } from "../lib/utils";
import { InfoHint } from "./ui/Hint";

export interface SocialSwarmProps {
  readonly context: readonly ContextItem[];
  readonly document: DocumentData | null | undefined;
  readonly evidence: readonly Evidence[];
  /** How the analysed item is named on the timeline: "This article", "This post", "This text". */
  readonly documentLabel: string;
}

function PostText({ post }: Readonly<{ post: SocialPost }>) {
  const text = post.item.text;
  if (!post.shared) return <>{text}</>;
  const [start, end] = post.shared;
  return (
    <>
      {text.slice(0, start)}
      <mark className="text-inherit rounded-[2px] bg-[var(--mark)] box-decoration-clone">{text.slice(start, end)}</mark>
      {text.slice(end)}
    </>
  );
}

/**
 * "Same wording on social media": the public posts that repeat the analysed text, one per account,
 * on a shared time axis. It shows the pattern (how many accounts, how fast) as measured facts; it
 * never labels an account as a bot.
 */
export function SocialSwarm({ context, document, evidence, documentLabel }: Readonly<SocialSwarmProps>) {
  const swarm = useMemo(() => buildSwarm(context, document, evidence), [context, document, evidence]);
  if (!swarm) return null;

  const documentAt = document?.published_at ? new Date(document.published_at).getTime() : null;
  const range = swarm.start !== null && swarm.end !== null ? swarm.end - swarm.start : 0;
  const position = (t: number) => (range > 0 && swarm.start !== null ? ((t - swarm.start) / range) * 100 : 50);

  const facts: { value: string; label: string }[] = [
    { value: String(swarm.accounts), label: swarm.accounts === 1 ? "account" : "accounts" },
    { value: String(swarm.platforms.length), label: swarm.platforms.length === 1 ? "platform" : "platforms" },
  ];
  if (swarm.spanMs !== null) facts.push({ value: formatSpan(swarm.spanMs), label: "first to last post" });
  if (swarm.burst) facts.push({ value: `${swarm.burst.count} in ${formatSpan(swarm.burst.spanMs)}`, label: "fastest burst" });

  return (
    <section aria-labelledby="swarm-heading" className="editorial-card rounded-xl p-4 sm:p-5 space-y-5">
      <div className="flex items-center gap-2">
        <h2 id="swarm-heading" className="text-sm font-medium text-[var(--fg-primary)]">
          Same wording on social media
        </h2>
        <InfoHint
          label="About repeated posts"
          content="Public posts that repeat this text word for word, one per account. Many accounts posting the same words within minutes is a common sign of coordinated or automated posting. We show the pattern; we do not label accounts."
        />
        <span className="ml-auto text-xs text-[var(--fg-muted)]">{swarm.platforms.join(", ")}</span>
      </div>

      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-3">
        {facts.map((f) => (
          <div key={f.label} className="space-y-0.5">
            <dt className="text-xs text-[var(--fg-muted)]">{f.label}</dt>
            <dd className="tabular text-lg font-semibold tracking-tight text-[var(--fg-primary)]">{f.value}</dd>
          </div>
        ))}
      </dl>

      {swarm.start !== null && swarm.end !== null && (
        <figure className="space-y-1.5">
          <div className="relative h-12" role="img" aria-label={`Timeline of ${swarm.posts.length} posts`}>
            <div className="absolute inset-x-0 top-1/2 h-px bg-[var(--border-strong)]" aria-hidden="true" />
            {documentAt !== null &&
              (() => {
                // Keep the label inside the track at both ends.
                const at = position(documentAt);
                const align = at < 12 ? "items-start" : at > 88 ? "items-end -translate-x-full" : "items-center -translate-x-1/2";
                return (
                  <div
                    className={cn("absolute top-0 bottom-0 flex flex-col", align)}
                    style={{ left: `${at}%` }}
                    title={`${documentLabel}: ${formatDateTime(document?.published_at) ?? ""}`}
                  >
                    <span className="text-[10px] font-medium text-[var(--accent)] whitespace-nowrap">{documentLabel}</span>
                    <span className="w-px flex-1 bg-[var(--accent)]" aria-hidden="true" />
                  </div>
                );
              })()}
            {swarm.posts.map((post, i) =>
              post.at === null ? null : (
                <a
                  key={post.item.id}
                  href={post.item.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  title={`${post.account} · ${formatDateTime(post.item.published_at) ?? ""}`}
                  className={cn(
                    "absolute h-2.5 w-2.5 -translate-x-1/2 rounded-full bg-[var(--indigo)] ring-2 ring-[var(--bg-surface)] hover:scale-125 transition-transform",
                    // Alternate rows so posts in the same minute stay visible.
                    i % 2 ? "top-[calc(50%+2px)]" : "top-[calc(50%-12px)]",
                  )}
                  style={{ left: `${position(post.at)}%` }}
                >
                  <span className="sr-only">{post.account}</span>
                </a>
              ),
            )}
          </div>
          <figcaption className="flex justify-between font-mono-num text-[11px] text-[var(--fg-muted)]">
            <span>{formatDateTime(new Date(swarm.start).toISOString())}</span>
            {range > 0 && <span>{formatDateTime(new Date(swarm.end).toISOString())}</span>}
          </figcaption>
        </figure>
      )}

      <ol className="divide-y divide-[var(--border-subtle)] border-t border-[var(--border-subtle)]">
        {swarm.posts.map((post) => (
          <li key={post.item.id} className="py-3 grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs min-w-0">
              <span className="font-mono-num text-[var(--fg-primary)] truncate">{post.account}</span>
              <span className={tagClass("neutral")}>{post.platform}</span>
              {/* Evidence cites up to 4 copies, so this marks the cited ones, not every copy counted. */}
              {post.citedAs.includes("text_reuse") && <span className={tagClass("indigo")}>Cited as evidence</span>}
            </div>
            <div className="text-right font-mono-num text-[11px] text-[var(--fg-muted)] whitespace-nowrap">
              {formatDateTime(post.item.published_at) ?? "no date"}
              {post.at !== null && documentAt !== null && (
                <span className="block">{formatOffset(post.at - documentAt)}</span>
              )}
            </div>
            <p className="col-span-2 text-[13px] leading-relaxed text-[var(--fg-secondary)] line-clamp-3 break-words">
              <PostText post={post} />
            </p>
            <a
              href={post.item.url}
              target="_blank"
              rel="noreferrer noopener"
              className="col-span-2 inline-flex items-center gap-1 text-xs text-[var(--accent)] hover:underline w-fit"
            >
              Open post
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          </li>
        ))}
      </ol>
    </section>
  );
}
