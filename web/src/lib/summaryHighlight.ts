export type SummaryTone = "plain" | "low" | "caution" | "high";

export interface SummarySegment {
  readonly text: string;
  readonly tone: SummaryTone;
}

interface CandidateMatch {
  readonly start: number;
  readonly end: number;
  readonly tone: SummaryTone;
  readonly priority: number;
}

/**
 * Neutral dimension names mandated by the `explain` prompt across supported languages.
 * Matched first as `plain` so words like "propaganda" or "coordinated campaign" inside a
 * dimension's fixed title never trigger a false red highlight on a 5% clean article.
 */
const PROTECTED_DIMENSION_PHRASES: readonly RegExp[] = [
  /\bsigns of propaganda in the content itself\b/gi,
  /\bsigns of a coordinated campaign\b/gi,
  /\bsegnali di propaganda nel contenuto stesso\b/gi,
  /\bsegnali di una campagna coordinata\b/gi,
  /\bAnzeichen von Propaganda im Inhalt selbst\b/gi,
  /\bAnzeichen einer koordinierten Kampagne\b/gi,
  /\bsignes de propagande dans le contenu lui-même\b/gi,
  /\bsignes d['’]une campagne coordonnée\b/gi,
  /\bseñales de propaganda en el propio contenido\b/gi,
  /\bseñales de una campaña coordinada\b/gi,
];

const LOW_SIGNAL_PATTERNS: readonly RegExp[] = [
  // Negations first so "no copied passages" / "not contradicted" stay green, never red.
  /\bno (?:signals|signs|evidence|indications|copied passages|shared tracking IDs|matches)(?: of [a-z -]{2,28})?(?: (?:were|was) found)?\b/gi,
  /\b(?:not|never) (?:contradicted|rated false|flagged)\b/gi,
  /\b(?:very )?low (?:confidence|probability|likelihood|percentage|score|baseline)\b/gi,
  /\b(?:minimal|negligible|few) (?:signs|signals|evidence)\b/gi,
  /\b(?:corroborated|supported|confirmed) by\b/gi,
  /\brated (?:true|accurate|correct)\b/gi,
  // Italian
  /\bnon sono stati trovati segnali\b/gi,
  /\bnessun(?:a|o)? (?:segnale|evidenza|prova|passaggio copiato|contraddizione)\b/gi,
  /\b(?:molto )?bass[ao] (?:confidenza|probabilità|percentuale|punteggio)\b/gi,
  /\b(?:confermat[oaie]|supportat[oaie]|corroborat[oaie]) da\b/gi,
  /\bvalutat[oaie] (?:ver[oa]|corrett[oa])\b/gi,
  // German / French / Spanish / Dutch / Polish / Portuguese
  /\bkeine (?:Signale|Hinweise|Belege|kopierten Passagen)(?: gefunden)?\b/gi,
  /\b(?:sehr )?(?:geringe|niedrige)[rn]? (?:Konfidenz|Wahrscheinlichkeit|Prozent\w*)\b/gi,
  /\baucun(?:e)? (?:signal|indice|preuve)(?: n['’]a été trouvé)?\b/gi,
  /\bfaible (?:confiance|probabilité|pourcentage)\b/gi,
  /\bno se encontraron señales\b/gi,
  /\bninguna señal\b/gi,
  /\bbaja (?:confianza|probabilidad)\b/gi,
  /\bgeen signalen(?: gevonden)?\b/gi,
  /\b(?:brak|żadnych) sygnałów\b/gi,
  /\bnão foram encontrados sinais\b/gi,
];

const CAUTION_PATTERNS: readonly RegExp[] = [
  /\babstained(?: from evaluating)?\b/gi,
  /\bnot enough evidence\b/gi,
  /\black of (?:comparable |independent |other |sufficient )?(?:reports|sources|coverage|evidence|items)\b/gi,
  /\black of\b/gi,
  /\btoo few (?:comparable |independent |other )?(?:reports|sources|items)\b/gi,
  /\binsufficient (?:evidence|coverage|reports|sources)\b/gi,
  /\bhumour or satire\b/gi,
  /\bsatire publication\b/gi,
  /\bevidence points both ways\b/gi,
  // Multilingual abstentions
  /\bsi è astenut[oa]\b/gi,
  /\bmancanza di (?:report|fonti|copertura|prove)(?: comparabili)?\b/gi,
  /\bmancanza di\b/gi,
  /\bprove insufficienti\b/gi,
  /\bhat sich enthalten\b/gi,
  /\bMangel an (?:vergleichbaren )?(?:Berichten|Quellen|Belegen)\b/gi,
  /\bnicht genügend Belege\b/gi,
  /\bs['’]est abstenue?\b/gi,
  /\bmanque de (?:rapports|sources|preuves)(?: comparables)?\b/gi,
  /\bpreuves insuffisantes\b/gi,
  /\bse abstuvo\b/gi,
  /\bfalta de (?:informes|fuentes|pruebas)(?: comparables)?\b/gi,
  /\bpruebas insuficientes\b/gi,
];

const HIGH_SIGNAL_PATTERNS: readonly RegExp[] = [
  /\b(?:very )?high (?:confidence|probability|likelihood|score)\b/gi,
  /\bhighly (?:likely|probable|charged)\b/gi,
  /\b(?:strong|substantial|clear|significant|pronounced|elevated) (?:signs|signals|evidence|indications)\b/gi,
  /\b(?:multiple |repeated )?persuasion techniques\b/gi,
  /\bfar more emotionally charged\b/gi,
  /\bmore emotionally charged than\b/gi,
  /\bcontradict(?:ed|s)(?: by)?\b/gi,
  /\brated (?:false|inaccurate|misleading|pants on fire|mostly false|unproven)\b/gi,
  /\b(?:debunked|fabricated|hoax)\b/gi,
  /\bcopied passages\b/gi,
  /\bshared tracking IDs?\b/gi,
  /\b(?:documented (?:propaganda )?network|Portal Kombat|VIGINUM)\b/gi,
  // Multilingual high signals
  /\b(?:molto )?alt[ao] (?:confidenza|probabilità|punteggio)\b/gi,
  /\b(?:forti|chiari|evidenti) (?:segnali|indizi)\b/gi,
  /\btecniche di persuasione\b/gi,
  /\bcontraddett[oaie](?: da)?\b/gi,
  /\bvalutat[oaie] (?:fals[oa]|fuorviante|inesatt[oa])\b/gi,
  /\bsmentit[oaie]\b/gi,
  /\bpassaggi copiati\b/gi,
  /\b(?:hohe|starke)[rn]? (?:Konfidenz|Wahrscheinlichkeit|Anzeichen|Hinweise)\b/gi,
  /\bals falsch(?: eingestuft| bewertet)?\b/gi,
  /\bwidersprochen\b/gi,
  /\b(?:forte|haute) (?:confiance|probabilité)\b/gi,
  /\bforts? signes\b/gi,
  /\bjugé(?:e|s)? (?:faux|fausse|trompeur)\b/gi,
  /\b(?:alta|fuerte) (?:confianza|probabilidad)\b/gi,
  /\bfuertes señales\b/gi,
  /\bcalificad[oa] como (?:fals[oa]|engaños[oa])\b/gi,
];

const PERCENTAGE_PATTERN = /\b(\d{1,3}(?:[.,]\d+)?)\s*%/g;

function collectRegexMatches(
  text: string,
  patterns: readonly RegExp[],
  tone: SummaryTone,
  priority: number,
): CandidateMatch[] {
  const out: CandidateMatch[] = [];
  for (const base of patterns) {
    const re = new RegExp(base.source, base.flags);
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      if (m[0].length === 0) {
        re.lastIndex += 1;
        continue;
      }
      out.push({
        start: m.index,
        end: m.index + m[0].length,
        tone,
        priority,
      });
    }
  }
  return out;
}

function collectPercentageMatches(text: string): CandidateMatch[] {
  const out: CandidateMatch[] = [];
  const re = new RegExp(PERCENTAGE_PATTERN.source, PERCENTAGE_PATTERN.flags);
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const num = Number.parseFloat(m[1].replace(",", "."));
    if (!Number.isFinite(num) || num < 0 || num > 100) continue;
    const tone: SummaryTone = num >= 60 ? "high" : num >= 30 ? "caution" : "low";
    out.push({
      start: m.index,
      end: m.index + m[0].length,
      tone,
      priority: 2,
    });
  }
  return out;
}

/**
 * Splits a summary paragraph into plain and semantically highlighted spans:
 * - `low` (green/teal): low percentages (<30%), "no signals", corroboration phrases
 * - `caution` (amber): abstentions, "lack of comparable reports", moderate 30-59% scores
 * - `high` (red): high percentages (>=60%), "strong signs", contradicted/rated-false claims, networks
 */
export function segmentSummaryHighlights(text: string): SummarySegment[] {
  if (!text) return [];

  const candidates: CandidateMatch[] = [
    ...collectRegexMatches(text, PROTECTED_DIMENSION_PHRASES, "plain", 0),
    ...collectRegexMatches(text, LOW_SIGNAL_PATTERNS, "low", 1),
    ...collectRegexMatches(text, CAUTION_PATTERNS, "caution", 1),
    ...collectRegexMatches(text, HIGH_SIGNAL_PATTERNS, "high", 1),
    ...collectPercentageMatches(text),
  ];

  if (candidates.length === 0) {
    return [{ text, tone: "plain" }];
  }

  // Sort by priority first (protected neutral dimension phrases claim their span before inner
  // words can match), then earliest start, then longest span.
  const byPriority = candidates
    .slice()
    .sort((a, b) => a.priority - b.priority || a.start - b.start || b.end - b.start - (a.end - a.start));

  const chosen: CandidateMatch[] = [];
  for (const cand of byPriority) {
    const overlaps = chosen.some((c) => cand.start < c.end && cand.end > c.start);
    if (!overlaps) {
      chosen.push(cand);
    }
  }
  chosen.sort((a, b) => a.start - b.start);

  const segments: SummarySegment[] = [];
  let cursor = 0;
  for (const span of chosen) {
    if (span.start > cursor) {
      segments.push({ text: text.slice(cursor, span.start), tone: "plain" });
    }
    segments.push({ text: text.slice(span.start, span.end), tone: span.tone });
    cursor = span.end;
  }
  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor), tone: "plain" });
  }

  // Merge adjacent plain segments.
  const merged: SummarySegment[] = [];
  for (const seg of segments) {
    if (!seg.text) continue;
    const prev = merged[merged.length - 1];
    if (prev && prev.tone === "plain" && seg.tone === "plain") {
      merged[merged.length - 1] = { text: prev.text + seg.text, tone: "plain" };
    } else {
      merged.push(seg);
    }
  }
  return merged;
}
