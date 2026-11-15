import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { GraphIndex } from "../../lib/graph";
import { buttonClass, SECTION_LABEL, tagClass } from "../../lib/ui";
import { Favicon } from "../ui/Favicon";
import { Tie } from "./TieEvidence";

export interface OutletInspectorProps {
  readonly index: GraphIndex;
  /** The open outlet, or null when closed. */
  readonly domain: string | null;
  readonly onOpenOutlet: (domain: string) => void;
  readonly onClose: () => void;
}

/** One outlet's attributes and every tie it has, with the evidence inline. No score. */
export function OutletInspector({ index, domain, onOpenOutlet, onClose }: Readonly<OutletInspectorProps>) {
  const outlet = domain ? index.outlets.get(domain) : undefined;
  const ties = domain ? (index.ties.get(domain) ?? []) : [];

  return (
    <Dialog.Root open={domain !== null} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/30 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed right-0 top-0 z-50 h-[100dvh] w-full sm:w-[min(560px,100vw)] overflow-y-auto border-l border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 sm:p-6 shadow-[var(--shadow-floating)] outline-none">
          <div className="flex items-start justify-between gap-4">
            <Dialog.Title className="flex items-center gap-2 min-w-0">
              {domain && <Favicon domain={domain} size={18} />}
              <span className="font-mono-num text-lg truncate">{domain}</span>
            </Dialog.Title>
            <Dialog.Close asChild>
              <button type="button" aria-label="Close" className={buttonClass("ghost", "icon", "-mr-2 -mt-1")}>
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </Dialog.Close>
          </div>
          <Dialog.Description className="mt-1 text-[13px] text-[var(--fg-secondary)]">
            What this site shares with others in the stored analyses. A tie is a trace, not a judgement of the site.
          </Dialog.Description>

          {outlet ? (
            <>
              <dl className="mt-5 grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1.5 text-[13px]">
                <Attribute term="Operator" value={outlet.operator} mono />
                {outlet.outlet_type && <Attribute term="Type" value={outlet.outlet_type.replace(/_/g, " ")} />}
                {outlet.country && <Attribute term="Country" value={outlet.country} />}
                <Attribute
                  term="Seen in"
                  value={`${outlet.articles} ${outlet.articles === 1 ? "article" : "articles"}, ${outlet.analysed} analysed`}
                />
                <Attribute term="Group" value={outlet.cluster === null ? "none" : `#${outlet.cluster}`} />
                {outlet.known_network && (
                  <>
                    <dt className="text-[var(--fg-muted)]">Published list</dt>
                    <dd>
                      <span className={tagClass("caution")}>
                        {outlet.known_network === "portal_kombat"
                          ? "VIGINUM, Portal Kombat"
                          : outlet.known_network.replace(/_/g, " ")}
                      </span>
                    </dd>
                  </>
                )}
              </dl>

              <section className="mt-6 space-y-1">
                <h2 className={SECTION_LABEL}>
                  {ties.length} {ties.length === 1 ? "tie" : "ties"}
                </h2>
                {ties.length === 0 ? (
                  <p className="text-[13px] text-[var(--fg-secondary)]">No shared trace with another site.</p>
                ) : (
                  <ul>
                    {ties.map((edge) => (
                      <Tie key={`${edge.a}|${edge.b}`} edge={edge} from={outlet.domain} onOpenOutlet={onOpenOutlet} />
                    ))}
                  </ul>
                )}
              </section>
            </>
          ) : (
            domain && (
              <p className="mt-5 text-[13px] text-[var(--fg-secondary)]">This site is not in the graph.</p>
            )
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Attribute({ term, value, mono }: Readonly<{ term: string; value: string; mono?: boolean }>) {
  return (
    <>
      <dt className="text-[var(--fg-muted)]">{term}</dt>
      <dd className={mono ? "font-mono-num" : undefined}>{value}</dd>
    </>
  );
}
