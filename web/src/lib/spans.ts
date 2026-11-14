import type { Claim, Evidence, Span } from "./contracts";

export interface SpanAnnotation {
  readonly id: string;
  readonly kind: "claim" | "evidence";
  readonly span: Span;
  readonly label: string;
}

export interface ParagraphSegment {
  readonly start: number;
  readonly end: number;
  readonly text: string;
  readonly annotations: readonly SpanAnnotation[];
}

/**
 * Slices a string by Unicode code-point offsets (`Array.from(paragraph)`),
 * matching Python's `str[start:end]` contract (`contracts/ts/api.d.ts:496`).
 */
export function sliceCodePoints(paragraph: string, start: number, end: number): string {
  const cps = Array.from(paragraph);
  const clampedStart = Math.max(0, Math.min(start, cps.length));
  const clampedEnd = Math.max(clampedStart, Math.min(end, cps.length));
  return cps.slice(clampedStart, clampedEnd).join("");
}

/**
 * Splits a single paragraph into contiguous, non-overlapping code-point segments,
 * preserving arbitrary overlapping Claim and Evidence spans without text duplication.
 */
export function segmentParagraph(
  paragraph: string,
  paragraphIndex: number,
  annotations: readonly SpanAnnotation[],
): ParagraphSegment[] {
  const cps = Array.from(paragraph);
  const len = cps.length;
  if (len === 0) {
    return [];
  }

  const relevant = annotations
    .filter((a) => a.span.paragraph === paragraphIndex)
    .map((a) => {
      const start = Math.max(0, Math.min(a.span.start, len));
      const end = Math.max(start, Math.min(a.span.end, len));
      return { ...a, span: { ...a.span, start, end } };
    })
    .filter((a) => a.span.end > a.span.start);

  if (relevant.length === 0) {
    return [{ start: 0, end: len, text: paragraph, annotations: [] }];
  }

  const cuts = new Set<number>([0, len]);
  for (const ann of relevant) {
    cuts.add(ann.span.start);
    cuts.add(ann.span.end);
  }
  const sortedCuts = Array.from(cuts).sort((a, b) => a - b);

  const segments: ParagraphSegment[] = [];
  for (let i = 0; i < sortedCuts.length - 1; i++) {
    const segStart = sortedCuts[i]!;
    const segEnd = sortedCuts[i + 1]!;
    if (segEnd <= segStart) continue;
    const active = relevant.filter((a) => a.span.start <= segStart && a.span.end >= segEnd);
    segments.push({
      start: segStart,
      end: segEnd,
      text: cps.slice(segStart, segEnd).join(""),
      annotations: active,
    });
  }
  return segments;
}

export function collectDocumentAnnotations(
  claims: readonly Claim[],
  evidence: readonly Evidence[],
): SpanAnnotation[] {
  const out: SpanAnnotation[] = [];
  for (const claim of claims) {
    out.push({
      id: claim.id,
      kind: "claim",
      span: claim.span,
      label: `Claim ${claim.id}`,
    });
  }
  for (const item of evidence) {
    for (const ref of item.source_refs) {
      if (ref.kind === "document") {
        out.push({
          id: item.id,
          kind: "evidence",
          span: ref.span,
          label: item.detail,
        });
      }
    }
  }
  return out;
}
