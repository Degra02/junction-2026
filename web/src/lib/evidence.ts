import type {
  ContextItem,
  DimensionKey,
  DocumentData,
  Evidence,
  Family,
  Score,
  SourceProfile,
} from "./contracts";
import { formatDomainAge } from "./format";
import { FAMILY_LABELS, OUTLET_TYPE_LABELS, networkLabel, signalLabel } from "./labels";
import { sliceCodePoints } from "./spans";

export function cleanDomain(raw: string | null | undefined): string {
  if (!raw) return "";
  const trimmed = raw.trim().toLowerCase();
  try {
    if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
      return new URL(trimmed).hostname.replace(/^www\./, "");
    }
  } catch {
    // Fall back to string strip
  }
  return trimmed.replace(/^www\./, "").split("/")[0] ?? "";
}

export interface ResolvedSourceCard {
  readonly kind: "context" | "document" | "url";
  readonly domain: string;
  readonly title: string;
  readonly quote: string | null;
  readonly url: string | null;
  readonly paragraphIndex: number | null;
  readonly outletTypeLabel: string | null;
  readonly outletTypeTone: "neutral" | "teal" | "caution" | null;
  readonly knownNetworkLabel: string | null;
  readonly domainAge: string | null;
  readonly factCheckRating: string | null;
  readonly factCheckPublisher: string | null;
}

export interface CitationChipMeta {
  readonly evidenceId: string;
  /** Publisher-first or signal-first human-readable label (never raw `[s1]`). */
  readonly primaryLabel: string;
  /** Additional source count beyond the primary (`+2`). */
  readonly extraCount: number;
  readonly familyLabel: string;
  readonly signalLabel: string;
  readonly detail: string;
  readonly tone: "accent" | "teal" | "caution" | "neutral";
  readonly sources: readonly ResolvedSourceCard[];
}

export function resolveEvidenceSources(
  ev: Evidence,
  document: DocumentData | null | undefined,
  context: readonly ContextItem[],
  sources: readonly SourceProfile[],
): ResolvedSourceCard[] {
  const contextMap = new Map(context.map((c) => [c.id, c]));
  const sourceMap = new Map(sources.map((s) => [cleanDomain(s.domain), s]));
  const cards: ResolvedSourceCard[] = [];

  for (const ref of ev.source_refs) {
    if (ref.kind === "context") {
      const ctx = contextMap.get(ref.id);
      const dom = cleanDomain(ctx?.outlet ?? ctx?.url) || "external source";
      const profile = sourceMap.get(dom);
      const typeMeta = profile?.outlet_type ? OUTLET_TYPE_LABELS[profile.outlet_type] : null;
      cards.push({
        kind: "context",
        domain: dom,
        title: ctx?.title || ctx?.fact_check?.claim || dom,
        quote:
          ref.quote ||
          (ctx?.text ? `${Array.from(ctx.text).slice(0, 180).join("")}${ctx.text.length > 180 ? "…" : ""}` : null),
        url: ctx?.url ?? null,
        paragraphIndex: null,
        outletTypeLabel: typeMeta?.label ?? null,
        outletTypeTone: typeMeta?.tone ?? null,
        knownNetworkLabel: profile?.known_network ? networkLabel(profile.known_network) : null,
        domainAge: formatDomainAge(
          profile?.registered_at,
          profile?.first_cert_at,
          document?.published_at ?? ctx?.published_at,
        ),
        factCheckRating: ctx?.fact_check?.rating ?? null,
        factCheckPublisher: ctx?.fact_check?.publisher ?? null,
      });
    } else if (ref.kind === "document") {
      const para = document?.paragraphs[ref.span.paragraph];
      const snippet =
        para !== undefined ? sliceCodePoints(para, ref.span.start, ref.span.end) : null;
      const dom = cleanDomain(document?.outlet ?? document?.url) || "Analysed text";
      const profile = sourceMap.get(dom);
      const typeMeta = profile?.outlet_type ? OUTLET_TYPE_LABELS[profile.outlet_type] : null;
      cards.push({
        kind: "document",
        domain: dom,
        title: `Paragraph ${ref.span.paragraph + 1} in analysed text`,
        quote: snippet,
        url: document?.url ?? null,
        paragraphIndex: ref.span.paragraph,
        outletTypeLabel: typeMeta?.label ?? null,
        outletTypeTone: typeMeta?.tone ?? null,
        knownNetworkLabel: profile?.known_network ? networkLabel(profile.known_network) : null,
        domainAge: formatDomainAge(
          profile?.registered_at,
          profile?.first_cert_at,
          document?.published_at,
        ),
        factCheckRating: null,
        factCheckPublisher: null,
      });
    } else if (ref.kind === "url") {
      const dom = cleanDomain(ref.url) || "Registry record";
      const profile = sourceMap.get(dom);
      const typeMeta = profile?.outlet_type ? OUTLET_TYPE_LABELS[profile.outlet_type] : null;
      cards.push({
        kind: "url",
        domain: dom,
        title: ref.url.includes("rdap")
          ? `RDAP domain registration (${dom})`
          : ref.url.includes("crt.sh")
            ? `Certificate Transparency log (${dom})`
            : `Source record (${dom})`,
        quote: ev.detail,
        url: ref.url,
        paragraphIndex: null,
        outletTypeLabel: typeMeta?.label ?? null,
        outletTypeTone: typeMeta?.tone ?? null,
        knownNetworkLabel: profile?.known_network ? networkLabel(profile.known_network) : null,
        domainAge: formatDomainAge(
          profile?.registered_at,
          profile?.first_cert_at,
          document?.published_at,
        ),
        factCheckRating: null,
        factCheckPublisher: null,
      });
    }
  }

  return cards;
}

export function resolveCitationChip(
  ev: Evidence,
  document: DocumentData | null | undefined,
  context: readonly ContextItem[],
  sources: readonly SourceProfile[],
): CitationChipMeta {
  const cards = resolveEvidenceSources(ev, document, context, sources);
  const contextCards = cards.filter((c) => c.kind === "context");
  const docCards = cards.filter((c) => c.kind === "document");
  const urlCards = cards.filter((c) => c.kind === "url");

  let primaryLabel: string;
  let extraCount = 0;

  if (contextCards.length > 0 && contextCards[0]) {
    const distinctDomains = Array.from(new Set(contextCards.map((c) => c.domain)));
    primaryLabel = distinctDomains[0] ?? contextCards[0].domain;
    extraCount = Math.max(0, distinctDomains.length - 1);
  } else if (docCards.length > 0 && docCards[0]) {
    const shortSignal = signalLabel(ev.signal).split(" ")[0] ?? "Passage";
    const pNum = docCards[0].paragraphIndex !== null ? `¶${docCards[0].paragraphIndex + 1}` : "text";
    primaryLabel = `${shortSignal} · ${pNum}`;
    extraCount = Math.max(0, docCards.length - 1);
  } else if (urlCards.length > 0 && urlCards[0]) {
    primaryLabel = urlCards[0].domain;
    extraCount = Math.max(0, urlCards.length - 1);
  } else {
    primaryLabel = FAMILY_LABELS[ev.family].name;
  }

  const isProtective =
    ev.signal === "rated_true" ||
    ev.signal === "outlet_wire_service" ||
    ev.signal === "outlet_fact_checker" ||
    ev.signal === "outlet_national" ||
    (ev.signal === "tone_vs_peers" && ev.value < 0);

  const isNetworkOrCaution =
    ev.family === "known_networks" ||
    ev.signal === "rated_false" ||
    ev.signal === "shared_tracking_id";

  return {
    evidenceId: ev.id,
    primaryLabel,
    extraCount,
    familyLabel: FAMILY_LABELS[ev.family].name,
    signalLabel: signalLabel(ev.signal),
    detail: ev.detail,
    tone: isProtective ? "teal" : isNetworkOrCaution ? "caution" : "accent",
    sources: cards,
  };
}

export function sigmoid(z: number): number {
  if (z >= 0) {
    const ez = Math.exp(-z);
    return 1 / (1 + ez);
  }
  const ez = Math.exp(z);
  return ez / (1 + ez);
}

export function logit(p: number): number {
  const clamped = Math.max(1e-6, Math.min(1 - 1e-6, p));
  return Math.log(clamped / (1 - clamped));
}

export interface WaterfallStep {
  readonly key: string;
  readonly family: Family | null;
  readonly label: string;
  readonly hint: string;
  readonly logOddsDelta: number;
  readonly probBefore: number;
  readonly probAfter: number;
  readonly evidenceIds: readonly string[];
}

/**
 * Projects logistic-regression log-odds contributions (`w_f * v_f`) onto cumulative
 * probability space `σ(b + Σ c_i)` so non-technical readers see exactly how each signal
 * family moves the score from the baseline prior to the final confidence percentage.
 */
export function computeWaterfallSteps(
  dimension: DimensionKey,
  score: Score,
  cappedAt85: boolean,
): {
  readonly intercept: number;
  readonly baselineProb: number;
  readonly finalProb: number;
  readonly steps: readonly WaterfallStep[];
} {
  const defaultIntercept = dimension === "single" ? -2.0 : -2.5;
  const sumContrib = score.breakdown.reduce((acc, b) => acc + b.contribution, 0);

  let intercept = defaultIntercept;
  if (
    !score.abstained &&
    score.confidence !== null &&
    score.confidence !== undefined &&
    !(cappedAt85 && Math.abs(score.confidence - 0.85) < 1e-3)
  ) {
    intercept = logit(score.confidence) - sumContrib;
  }

  const baselineProb = sigmoid(intercept);

  // Order non-zero contributions by magnitude descending so dominant drivers come first, keeping 0s at end
  const sorted = score.breakdown.slice().sort((a, b) => {
    const absDiff = Math.abs(b.contribution) - Math.abs(a.contribution);
    if (Math.abs(absDiff) > 1e-4) return absDiff;
    return 0;
  });

  let runningZ = intercept;
  const steps: WaterfallStep[] = sorted.map((row) => {
    const probBefore = sigmoid(runningZ);
    runningZ += row.contribution;
    const probAfter = sigmoid(runningZ);
    const meta = FAMILY_LABELS[row.family];
    return {
      key: row.family,
      family: row.family,
      label: meta.name,
      hint: meta.hint,
      logOddsDelta: row.contribution,
      probBefore,
      probAfter,
      evidenceIds: row.evidence_ids,
    };
  });

  const uncappedFinal = sigmoid(runningZ);
  const finalProb =
    score.confidence !== null && score.confidence !== undefined
      ? score.confidence
      : cappedAt85
        ? Math.min(0.85, uncappedFinal)
        : uncappedFinal;

  return {
    intercept,
    baselineProb,
    finalProb,
    steps,
  };
}
