import { useCallback, useEffect, useState } from "react";
import {
  Bookmark,
  Check,
  Copy,
  Download,
  FileText,
  Globe,
  MousePointerClick,
  PanelRight,
  Terminal,
} from "lucide-react";
import { getHealth } from "../lib/api";
import type { Health } from "../lib/contracts";
import { SECTION_LABEL, buttonClass, tagClass } from "../lib/ui";
import { cn } from "../lib/utils";

export type ExtensionPageProps = Record<string, never>;

export function ExtensionPage(_props: Readonly<ExtensionPageProps>) {
  const [health, setHealth] = useState<Health | null>(null);
  const [copiedKey, setCopiedKey] = useState<"endpoint" | "curl" | null>(null);

  const origin = typeof window !== "undefined" ? window.location.origin : "https://the4thlover.tech";

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then(setHealth)
      .catch(() => {
        // Standalone UI preview
      });
    return () => controller.abort();
  }, []);

  const bookmarkletCode = `javascript:(()=>{const s=(window.getSelection?window.getSelection().toString():"").trim();const b=${JSON.stringify(origin)};const u=s?b+"/?text="+encodeURIComponent(s.slice(0,8000))+"&autorun=1":b+"/?url="+encodeURIComponent(location.href)+"&autorun=1";window.open(u,"_blank","noopener");})();`;

  const setBookmarkletHref = useCallback(
    (node: HTMLAnchorElement | null) => {
      if (node) {
        node.setAttribute("href", bookmarkletCode);
      }
    },
    [bookmarkletCode],
  );

  const curlSnippet = `curl -sS -X POST "${origin}/api/analyses" \\
  -H "Content-Type: application/json" \\
  -d '{"kind":"url","value":"https://example.com/article"}'`;

  async function copyText(key: "endpoint" | "curl", text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      window.setTimeout(() => setCopiedKey((prev) => (prev === key ? null : prev)), 1800);
    } catch {
      // Clipboard blocked in non-secure context
    }
  }

  return (
    <div className="max-w-[880px] mx-auto space-y-12">
      <header className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className={tagClass("accent", { mono: true })}>Manifest V3 · Chrome · Brave · Edge</span>
          {health && (
            <span className={tagClass(health.status === "ok" ? "teal" : "caution", { mono: true })}>
              API {health.status === "ok" ? "online" : "degraded"} · {health.pipeline_version.slice(0, 11)}
            </span>
          )}
        </div>

        <h1 className="display text-3xl sm:text-[42px] leading-[1.08] text-[var(--fg-primary)]">
          Check any story where you read it.
        </h1>

        <p className="text-[15px] text-[var(--fg-secondary)] max-w-[62ch] leading-relaxed">
          Connect your browser directly to this Decode the Noise workspace. Cross-check open articles,
          highlighted claims, or logged-in social feeds without switching tabs or copying links by hand.
        </p>

        <div className="pt-1 flex flex-wrap items-center gap-3">
          <a
            href="/decode-the-noise-extension.zip"
            download="decode-the-noise-extension.zip"
            className={buttonClass("primary", "lg")}
          >
            <Download className="h-4 w-4" aria-hidden="true" />
            Download extension (.zip)
          </a>

          <div className="inline-flex items-center gap-1.5 h-10 px-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-xs">
            <span className="text-[var(--fg-muted)]">Server:</span>
            <code className="font-mono-num text-[var(--fg-primary)]">{origin}</code>
            <button
              type="button"
              onClick={() => void copyText("endpoint", origin)}
              className={buttonClass("ghost", "icon", "h-6 w-6 ml-0.5")}
              aria-label="Copy server URL"
              title="Copy server URL for extension settings"
            >
              {copiedKey === "endpoint" ? (
                <Check className="h-3.5 w-3.5 text-[var(--teal)]" aria-hidden="true" />
              ) : (
                <Copy className="h-3.5 w-3.5" aria-hidden="true" />
              )}
            </button>
          </div>
        </div>
      </header>

      <section className="space-y-3">
        <h2 className={SECTION_LABEL}>What the extension adds</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 space-y-2 shadow-[var(--shadow-editorial)]">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-[var(--fg-primary)]">
              <PanelRight className="h-4 w-4 text-[var(--accent)] shrink-0" aria-hidden="true" />
              <span>Popup &amp; docked side panel</span>
            </div>
            <p className="text-xs text-[var(--fg-secondary)] leading-relaxed">
              Streams all 8 pipeline stages live over SSE alongside the article and jumps straight to the
              cached waterfall breakdown on this site.
            </p>
          </div>

          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 space-y-2 shadow-[var(--shadow-editorial)]">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-[var(--fg-primary)]">
              <MousePointerClick className="h-4 w-4 text-[var(--indigo)] shrink-0" aria-hidden="true" />
              <span>Right-click claim check</span>
            </div>
            <p className="text-xs text-[var(--fg-secondary)] leading-relaxed">
              Highlight any headline, quote, or paragraph—or right-click any outbound link—and send it
              straight into cross-outlet verification.
            </p>
          </div>

          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 space-y-2 shadow-[var(--shadow-editorial)]">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-[var(--fg-primary)]">
              <FileText className="h-4 w-4 text-[var(--teal)] shrink-0" aria-hidden="true" />
              <span>Reader DOM capture</span>
            </div>
            <p className="text-xs text-[var(--fg-secondary)] leading-relaxed">
              Reads visible paragraphs directly from your open tab when social feeds or subscriber pages
              refuse server-side HTTP fetchers.
            </p>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 space-y-4 shadow-[var(--shadow-editorial)]">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-[var(--fg-primary)]">
              Install unpacked in 30 seconds
            </h2>
            <Globe className="h-4 w-4 text-[var(--fg-muted)]" aria-hidden="true" />
          </div>

          <ol className="space-y-2.5 text-[13px] text-[var(--fg-secondary)] list-decimal pl-4">
            <li>
              Download and unzip{" "}
              <code className="font-mono-num text-xs text-[var(--fg-primary)]">
                decode-the-noise-extension.zip
              </code>
              .
            </li>
            <li>
              Open{" "}
              <code className="font-mono-num text-xs px-1.5 py-0.5 rounded bg-[var(--bg-subtle)] text-[var(--fg-primary)]">
                chrome://extensions
              </code>{" "}
              (or <code className="font-mono-num text-xs">brave://extensions</code> /{" "}
              <code className="font-mono-num text-xs">edge://extensions</code>) and switch on{" "}
              <strong className="font-medium text-[var(--fg-primary)]">Developer mode</strong>.
            </li>
            <li>
              Click <strong className="font-medium text-[var(--fg-primary)]">Load unpacked</strong> and
              select the unzipped folder. It connects to{" "}
              <code className="font-mono-num text-xs text-[var(--fg-primary)]">{origin}</code>{" "}
              automatically.
            </li>
          </ol>
        </section>

        <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 space-y-4 shadow-[var(--shadow-editorial)]">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-[var(--fg-primary)]">
              Zero-install bookmarklet (Safari &amp; Firefox)
            </h2>
            <Bookmark className="h-4 w-4 text-[var(--fg-muted)]" aria-hidden="true" />
          </div>

          <p className="text-[13px] text-[var(--fg-secondary)] leading-relaxed">
            Drag this button to your bookmarks bar. Click it on any article—or highlight a passage first—to
            open an instant check on this server:
          </p>

          <div className="pt-1 flex items-center gap-3">
            <a
              ref={setBookmarkletHref}
              onClick={(e) => e.preventDefault()}
              draggable
              className={cn(buttonClass("secondary", "md"), "cursor-grab active:cursor-grabbing")}
              title="Drag me to your browser bookmarks bar"
            >
              <Bookmark className="h-3.5 w-3.5 text-[var(--accent)]" aria-hidden="true" />
              Check with Decode the Noise
            </a>
            <span className="text-xs text-[var(--fg-muted)]">← drag to bookmarks bar</span>
          </div>
        </section>
      </div>

      <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 space-y-3 shadow-[var(--shadow-editorial)]">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4 text-[var(--fg-muted)]" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-[var(--fg-primary)]">
              Automate from CMS, n8n, or moderation webhooks
            </h2>
          </div>
          <button
            type="button"
            onClick={() => void copyText("curl", curlSnippet)}
            className={buttonClass("ghost", "sm")}
          >
            {copiedKey === "curl" ? (
              <>
                <Check className="h-3.5 w-3.5 text-[var(--teal)]" aria-hidden="true" />
                Copied
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                Copy curl
              </>
            )}
          </button>
        </div>

        <pre className="overflow-x-auto rounded-lg bg-[var(--bg-subtle)] p-3 font-mono-num text-xs text-[var(--fg-primary)] leading-relaxed">
          <code>{curlSnippet}</code>
        </pre>
      </section>
    </div>
  );
}
