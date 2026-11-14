import { useMemo } from "react";
import { Lightbulb } from "lucide-react";
import type { DocumentData, Evidence, StepState } from "../lib/contracts";
import { TECHNIQUE_GUIDE, signalLabel } from "../lib/labels";
import { sliceCodePoints } from "../lib/spans";
import { SECTION_LABEL, tagClass } from "../lib/ui";
import { InfoHint } from "./ui/Hint";

export interface TechniquesPanelProps {
  readonly evidence: readonly Evidence[];
  readonly document: DocumentData;
  /** State of `signals_single`: the panel only speaks once the techniques were checked. */
  readonly checked: StepState | undefined;
  /** Opens the article at the passages of this evidence item. */
  readonly onOpenPassage: (evidenceId: string) => void;
}

interface Passage {
  readonly paragraph: number;
  readonly text: string;
}

interface TechniqueRow {
  readonly evidence: Evidence;
  readonly name: string;
  readonly what: string | null;
  readonly spot: string | null;
  /** The model's technique names inside the category, as listed in the evidence detail. */
  readonly found: readonly string[];
  /** "3 of 9 paragraphs", from the evidence detail. */
  readonly extent: string | null;
  readonly passages: readonly Passage[];
}

const PASSAGE_CHARS = 240;

// `pipeline/signals/techniques.py` writes "<description> (<names>) in <n> of [the first ]<m> paragraph(s)."
const NAMES_RE = /\(([^)]+)\)\s+in\s+\d+/;
const EXTENT_RE = /in (\d+) of (the first )?(\d+) paragraphs?/;

function toRow(ev: Evidence, document: DocumentData): TechniqueRow {
  const guide = TECHNIQUE_GUIDE[ev.signal];
  const names = NAMES_RE.exec(ev.detail)?.[1];
  const extent = EXTENT_RE.exec(ev.detail);
  const passages: Passage[] = [];
  for (const ref of ev.source_refs) {
    if (ref.kind !== "document") continue;
    const para = document.paragraphs[ref.span.paragraph];
    if (para === undefined) continue;
    const text = sliceCodePoints(para, ref.span.start, ref.span.end).trim();
    if (text) passages.push({ paragraph: ref.span.paragraph, text });
  }
  return {
    evidence: ev,
    name: guide?.name ?? signalLabel(ev.signal),
    what: guide?.what ?? null,
    spot: guide?.spot ?? null,
    found: names ? names.split(",").map((n) => n.trim()).filter(Boolean) : [],
    extent: extent ? `${extent[1]} of ${extent[2] ? "the first " : ""}${extent[3]} paragraphs` : null,
    passages,
  };
}

function clip(text: string): string {
  const chars = Array.from(text);
  return chars.length > PASSAGE_CHARS ? `${chars.slice(0, PASSAGE_CHARS).join("").trimEnd()}…` : text;
}

/**
 * "What the text does": the persuasion techniques found in the wording, each with what it is
 * and how to spot it. Shown whether or not the score abstains: it describes the text, it does
 * not need other coverage, and it is not a verdict (D4).
 */
export function TechniquesPanel({ evidence, document, checked, onOpenPassage }: Readonly<TechniquesPanelProps>) {
  const rows = useMemo(
    () =>
      evidence
        .filter((e) => e.family === "techniques")
        .slice()
        .sort((a, b) => b.value - a.value)
        .map((e) => toRow(e, document)),
    [evidence, document],
  );

  if (checked !== "done") return null;

  return (
    <section aria-labelledby="techniques-heading" className="editorial-card rounded-xl p-4 sm:p-5 space-y-4">
      <div className="flex items-center gap-2">
        <h2 id="techniques-heading" className="text-sm font-medium text-[var(--fg-primary)]">
          What the text does
        </h2>
        <InfoHint
          label="About technique detection"
          content="A multilingual persuasion-technique model reads every paragraph. It describes the wording, it is not a verdict, and it can miss or over-flag: read the passages yourself."
        />
        {rows.length > 0 && (
          <span className="ml-auto font-mono-num text-xs text-[var(--fg-muted)]">
            {rows.length} technique{rows.length === 1 ? "" : "s"}
          </span>
        )}
      </div>

      {rows.length === 0 ? (
        <p className="text-[13px] text-[var(--fg-secondary)]">No persuasion techniques found in the wording.</p>
      ) : (
        <ul className="divide-y divide-[var(--border-subtle)]">
          {rows.map((row) => {
            const [first, ...rest] = row.passages;
            return (
              <li key={row.evidence.id} className="py-4 first:pt-0 last:pb-0 space-y-2">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <h3 className="text-sm font-medium text-[var(--fg-primary)]">{row.name}</h3>
                  {row.extent && <span className="font-mono-num text-xs text-[var(--fg-muted)]">{row.extent}</span>}
                </div>
                {row.what && <p className="text-[13px] text-[var(--fg-secondary)] leading-relaxed">{row.what}</p>}
                {row.found.length > 0 && (
                  <div className="flex flex-wrap gap-1" aria-label="Techniques found">
                    {row.found.map((name) => (
                      <span key={name} className={tagClass("neutral")}>
                        {name}
                      </span>
                    ))}
                  </div>
                )}
                {first && (
                  <button
                    type="button"
                    onClick={() => onOpenPassage(row.evidence.id)}
                    title="Show this passage in the article"
                    className="group block w-full text-left rounded-lg border-l-2 border-[var(--mark-strong)] bg-[var(--bg-subtle)] hover:bg-[var(--bg-hover)] px-3 py-2 cursor-pointer"
                  >
                    <span className="font-mono-num text-[11px] text-[var(--fg-muted)] mr-2">¶{first.paragraph + 1}</span>
                    <span className="font-serif text-[15px] leading-relaxed text-[var(--fg-primary)] line-clamp-3">
                      {clip(first.text)}
                    </span>
                  </button>
                )}
                {rest.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1 text-xs text-[var(--fg-muted)]">
                    <span>Also in</span>
                    {rest.map((p) => (
                      <button
                        key={p.paragraph}
                        type="button"
                        onClick={() => onOpenPassage(row.evidence.id)}
                        title={clip(p.text)}
                        className={tagClass("neutral", { mono: true }, "cursor-pointer hover:border-[var(--border-strong)]")}
                      >
                        ¶{p.paragraph + 1}
                      </button>
                    ))}
                  </div>
                )}
                {row.spot && (
                  <p className="flex items-start gap-1.5 text-[13px] text-[var(--fg-secondary)]">
                    <Lightbulb className="h-3.5 w-3.5 mt-0.5 shrink-0 text-[var(--caution)]" aria-hidden="true" />
                    <span>
                      <span className="font-medium text-[var(--fg-primary)]">Spot it: </span>
                      {row.spot}
                    </span>
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {rows.length > 0 && (
        <p className={SECTION_LABEL}>Describes the wording only; the scores above also weigh the other coverage.</p>
      )}
    </section>
  );
}
