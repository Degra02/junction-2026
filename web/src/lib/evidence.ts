import type {
  Analysis,
  ContextItem,
  DimensionKey,
  DocumentData,
  Evidence,
  Family,
  Score,
  SourceProfile,
  StageName,
} from "./contracts";
import { formatDomainAge } from "./format";
import {
  ALL_STAGES,
  FAMILY_LABELS,
  OUTLET_TYPE_LABELS,
  STAGE_LABELS,
  languageName,
  networkLabel,
  signalLabel,
} from "./labels";
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

export interface LiveActivityDescription {
  readonly headline: string;
  readonly subline: string;
  readonly activeStages: readonly StageName[];
  readonly completedCount: number;
  readonly totalCount: number;
  readonly progressFraction: number;
}

/**
 * Generates a crisp, human-readable one-sentence status summary of what the pipeline
 * is doing right now, incorporating live worker progress notes and hydrated artifacts.
 */
export function describeLiveActivity(analysis: Analysis): LiveActivityDescription {
  const stepMap = new Map(analysis.steps.map((s) => [s.name, s]));
  const totalCount = ALL_STAGES.length;
  const completedCount = ALL_STAGES.filter((name) => {
    const st = stepMap.get(name)?.state;
    return st === "done" || st === "skipped";
  }).length;

  const runningSteps = ALL_STAGES.map((n) => stepMap.get(n)).filter(
    (s): s is NonNullable<typeof s> => s !== undefined && s.state === "running",
  );
  const activeStages = runningSteps.map((s) => s.name);

  if (analysis.status === "queued") {
    const pos = analysis.queue_position ?? 1;
    return {
      headline: `Queued for analysis (position #${pos})…`,
      subline: "Waiting for an inference worker slot on the server.",
      activeStages: [],
      completedCount: 0,
      totalCount,
      progressFraction: 0.04,
    };
  }

  if (runningSteps.length > 0 && runningSteps[0]) {
    const primary = runningSteps[0];
    const stageMeta = STAGE_LABELS[primary.name];
    const liveNote = primary.detail?.trim() || null;

    let headline = stageMeta.activeVerb;
    let subline = liveNote ?? `Stage ${completedCount + 1} of ${totalCount}`;

    if (primary.name === "extract") {
      headline =
        analysis.input.kind === "url"
          ? `Fetching article and extracting clean text from ${cleanDomain(analysis.input.value) || "URL"}…`
          : "Parsing pasted text and identifying its language…";
      subline = liveNote ?? "Stripping navigation boilerplate and locating tracking tags";
    } else if (primary.name === "understand") {
      const lang = analysis.language ? languageName(analysis.language.code) : null;
      headline = `Extracting verifiable claims and building ${lang && lang !== "English" ? `${lang} + English` : "search"} queries…`;
      subline =
        liveNote ??
        (analysis.document
          ? `Reading ${analysis.document.paragraphs.length} paragraphs${analysis.document.outlet ? ` from ${analysis.document.outlet}` : ""}`
          : "Identifying the core event and assertions");
    } else if (primary.name === "retrieve") {
      const qCount = analysis.queries.length;
      headline = liveNote
        ? `Searching live web sources — ${liveNote.charAt(0).toLowerCase()}${liveNote.slice(1)}…`
        : `Searching news feeds, ClaimReview fact-checkers, and web archives${qCount > 0 ? ` across ${qCount} queries` : ""}…`;
      subline =
        analysis.queries.length > 0
          ? `Queries include “${analysis.queries[0]?.text}”`
          : "Querying curated RSS, Google Fact Check API, Oxylabs, and domain registries";
    } else if (primary.name === "story") {
      headline = `Clustering ${analysis.context.length || "retrieved"} articles to isolate coverage of the exact same event…`;
      subline = liveNote ?? "Computing multilingual semantic embeddings across retrieved outlets";
    } else if (
      primary.name === "signals_single" ||
      primary.name === "signals_coordinated"
    ) {
      const both = runningSteps.length > 1;
      const peerCount = analysis.context.filter((c) => c.in_story !== false).length;
      headline = both
        ? `Cross-checking ${analysis.claims.length || "key"} claims against ${peerCount || "peer"} reports and scanning for copy networks…`
        : stageMeta.activeVerb;
      subline =
        liveNote ??
        "Running multilingual NLI claim verification, persuasion classification, and 5-gram reuse checks";
    } else if (primary.name === "score") {
      headline = "Combining strongest signal per family into confidence scores…";
      subline = "Evaluating abstention thresholds and computing family log-odds contributions";
    } else if (primary.name === "explain") {
      headline = "Writing plain-language summary with verbatim quote verification…";
      subline = "Every cited reason is checked character-by-character against retrieved sources";
    }

    return {
      headline,
      subline,
      activeStages,
      completedCount,
      totalCount,
      progressFraction: Math.max(0.08, Math.min(0.95, (completedCount + 0.5) / totalCount)),
    };
  }

  return {
    headline:
      analysis.status === "failed"
        ? "Analysis stopped before completing all stages."
        : "Preparing pipeline stages…",
    subline: analysis.error ?? `${completedCount} of ${totalCount} stages complete`,
    activeStages: [],
    completedCount,
    totalCount,
    progressFraction: completedCount / totalCount,
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

export function describeConfidenceBand(
  confidence: number,
  evidenceCount: number,
): {
  readonly badge: string;
  readonly tone: "teal" | "neutral" | "accent" | "caution";
} {
  if (confidence < 0.16) {
    return {
      badge: evidenceCount === 0 ? "Baseline · No signals found" : "Minimal signal alignment",
      tone: "teal",
    };
  }
  if (confidence < 0.40) {
    return {
      badge: "Low signal alignment",
      tone: "neutral",
    };
  }
  if (confidence < 0.68) {
    return {
      badge: "Moderate signal alignment",
      tone: "accent",
    };
  }
  return {
    badge: "Strong signal alignment",
    tone: "accent",
  };
}
