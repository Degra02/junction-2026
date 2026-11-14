import { Link } from "react-router-dom";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { buttonClass } from "../lib/ui";

const STEPS: readonly { readonly title: string; readonly text: string }[] = [
  { title: "Read", text: "We fetch the article, or take your text, and pick out its checkable claims." },
  { title: "Search", text: "We look for other reports on the same event in news feeds, news search and fact-checks." },
  {
    title: "Compare",
    text: "Persuasion techniques, tone against the other reports, contradicted or fact-checked claims, copied passages, timing, shared trackers, documented networks.",
  },
  {
    title: "Score",
    text: "Two separate confidences: signs of propaganda in the content itself, and signs of a coordinated campaign. Every reason links to its source.",
  },
];

/** "How it works": what the tool does, what the numbers mean, what to know before pasting. */
export function HowItWorks({ triggerClassName }: Readonly<{ triggerClassName: string }>) {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <button type="button" className={triggerClassName}>
          How it works
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/30 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed left-1/2 top-[12vh] z-50 w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 max-h-[80vh] overflow-y-auto editorial-card rounded-xl p-6 shadow-[var(--shadow-floating)] outline-none">
          <div className="flex items-start justify-between gap-4">
            <Dialog.Title className="display text-2xl">How it works</Dialog.Title>
            <Dialog.Close asChild>
              <button type="button" aria-label="Close" className={buttonClass("ghost", "icon", "-mr-2 -mt-1")}>
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </Dialog.Close>
          </div>
          <Dialog.Description className="mt-1 text-[13px] text-[var(--fg-secondary)]">
            Paste a link or text. An analysis takes about a minute.
          </Dialog.Description>

          <ol className="mt-5 space-y-3.5">
            {STEPS.map((step, i) => (
              <li key={step.title} className="flex gap-3">
                <span className="font-mono-num text-xs text-[var(--fg-muted)] pt-0.5">{String(i + 1).padStart(2, "0")}</span>
                <p className="text-sm text-[var(--fg-secondary)]">
                  <span className="font-medium text-[var(--fg-primary)]">{step.title}.</span> {step.text}
                </p>
              </li>
            ))}
          </ol>

          <div className="mt-6 pt-5 border-t border-[var(--border-subtle)] space-y-2.5 text-sm text-[var(--fg-secondary)]">
            <p>
              <span className="font-medium text-[var(--fg-primary)]">The numbers are confidences, not verdicts.</span> They
              say how strongly documented signals are present.
            </p>
            <p>
              <span className="font-medium text-[var(--fg-primary)]">Not enough evidence</span> means too few other reports
              were found to compare against.
            </p>
            <p>Analyses are stored: anyone with the link can see the result.</p>
          </div>

          <div className="mt-6 flex justify-end gap-2">
            <Dialog.Close asChild>
              <Link to="/metrics" className={buttonClass("secondary", "md")}>
                How accurate is it?
              </Link>
            </Dialog.Close>
            <Dialog.Close asChild>
              <button type="button" className={buttonClass("primary", "md")}>
                Got it
              </button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
