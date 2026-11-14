import type {
  DimensionKey,
  Family,
  LanguageSupport,
  OutletType,
  StageName,
} from "./contracts";

export const ALL_STAGES: readonly StageName[] = [
  "extract",
  "understand",
  "retrieve",
  "story",
  "signals_single",
  "signals_coordinated",
  "score",
  "explain",
];

/** `label`: a finished or waiting step; `active`: the same step while it runs; `help`: what it does. */
export const STAGE_LABELS: Readonly<
  Record<StageName, { readonly label: string; readonly active: string; readonly help: string }>
> = {
  extract: {
    label: "Read the article",
    active: "Reading the article",
    help: "Fetches the page and keeps only the article text, its outlet and its language.",
  },
  understand: {
    label: "Found the claims and search terms",
    active: "Finding the claims and search terms",
    help: "Picks the checkable claims and writes search terms in the article's language and in English.",
  },
  retrieve: {
    label: "Searched other coverage",
    active: "Searching other coverage",
    help: "Searches news feeds, news search and fact-checkers, then reads every report it finds.",
  },
  story: {
    label: "Matched reports on the same event",
    active: "Matching reports on the same event",
    help: "Keeps only the reports about the same event; the rest are not compared.",
  },
  signals_single: {
    label: "Checked the content",
    active: "Checking the content",
    help: "Looks for persuasion techniques, compares the tone with other reports, and checks the claims against them and against fact-checks.",
  },
  signals_coordinated: {
    label: "Checked for coordination",
    active: "Checking for coordination",
    help: "Looks for passages copied by unrelated sites, publication timing, shared trackers and documented networks.",
  },
  score: {
    label: "Scored both dimensions",
    active: "Scoring both dimensions",
    help: "Combines the signals into one confidence per dimension, or says there is not enough evidence.",
  },
  explain: {
    label: "Wrote the explanation",
    active: "Writing the explanation",
    help: "Writes the summary and reasons; every quotation is checked against the sources.",
  },
};

export const DIMENSION_META: Readonly<
  Record<
    DimensionKey,
    {
      readonly title: string;
      readonly shortTitle: string;
      readonly subtitle: string;
      readonly families: readonly Family[];
    }
  >
> = {
  single: {
    title: "Signs of propaganda in the content itself",
    shortTitle: "Single actor",
    subtitle: "Persuasion techniques, tone against other reports, contradicted claims, fact-checks, outlet profile.",
    families: ["techniques", "tone", "claim_support", "fact_checks", "source_profile"],
  },
  coordinated: {
    title: "Signs of a coordinated campaign",
    shortTitle: "Coordinated",
    subtitle: "Copied passages on unrelated sites, timing, shared tracking IDs, documented networks.",
    families: ["text_reuse", "timing", "infrastructure", "known_networks"],
  },
};

export const FAMILY_LABELS: Readonly<
  Record<Family, { readonly name: string; readonly hint: string; readonly dimension: DimensionKey }>
> = {
  techniques: {
    name: "Persuasion techniques",
    hint: "Loaded wording, attacks, fear appeals, oversimplification",
    dimension: "single",
  },
  rhetoric: {
    name: "Rhetoric",
    hint: "Persuasion techniques, rated by a language model that sees the image",
    dimension: "single",
  },
  tone: {
    name: "Tone vs. other reports",
    hint: "Emotional charge against reports on the same event",
    dimension: "single",
  },
  claim_support: {
    name: "Claim corroboration",
    hint: "Claims supported or contradicted by other reports",
    dimension: "single",
  },
  fact_checks: {
    name: "Fact-checker reviews",
    hint: "Published fact-checks matching claims in the text",
    dimension: "single",
  },
  source_profile: {
    name: "Source profile",
    hint: "Domain age and outlet type",
    dimension: "single",
  },
  text_reuse: {
    name: "Copied passages",
    hint: "Unrelated sites publishing the same passages (wire copy excluded)",
    dimension: "coordinated",
  },
  timing: {
    name: "Publication timing",
    hint: "Copies published within 6 hours",
    dimension: "coordinated",
  },
  infrastructure: {
    name: "Shared infrastructure",
    hint: "Shared analytics or ad IDs, newly registered copying domains",
    dimension: "coordinated",
  },
  known_networks: {
    name: "Documented networks",
    hint: "On VIGINUM's Portal Kombat list",
    dimension: "coordinated",
  },
};

export const SIGNAL_LABELS: Readonly<Record<string, string>> = {
  attack_on_reputation: "Personal attacks or reputation framing",
  justification: "Flag-waving or moral justification",
  simplification: "False dilemma or causal oversimplification",
  distraction: "Whataboutism or topic deflection",
  call: "Slogans or calls to action",
  manipulative_wording: "Emotionally charged or loaded wording",
  tone_vs_peers: "Emotional intensity vs. story peers",
  contradicted: "Claim contradicted vs. supported across peers",
  unaddressed: "Claim not reported by peer outlets",
  rated_false: "Fact-checker rated claim false",
  rated_misleading: "Fact-checker rated claim misleading",
  rated_true: "Fact-checker rated claim accurate",
  domain_age_days: "Domain registration age at publication",
  outlet_wire_service: "Recognized news wire agency",
  outlet_national: "Established national newsroom",
  outlet_local: "Local or regional newsroom",
  outlet_partisan: "Politically partisan outlet",
  outlet_state_affiliated: "State-affiliated media outlet",
  outlet_fact_checker: "Signatory fact-checking organization",
  outlet_satire: "Satire or parody publication",
  copied_passages: "Near-duplicate passages on other sites",
  copies_within_window: "Copies published within 6 hours",
  shared_tracking_id: "Shared analytics or ad tracking ID",
  young_copying_domains: "Newly registered copying domains",
  listed_domain: "Listed in documented network registry",
};

/**
 * Reader's guide to the six technique categories of `pipeline/signals/techniques.py`
 * (SemEval-2023 persuasion techniques): what the category does, and one question that helps a
 * reader spot it without us. The `rhetoric` family (the same categories, rated by a language
 * model that also sees the image) uses the same signal names, so the guide serves both.
 */
export const TECHNIQUE_GUIDE: Readonly<
  Record<string, { readonly name: string; readonly what: string; readonly spot: string }>
> = {
  manipulative_wording: {
    name: "Loaded wording",
    what: "Charged, exaggerated, vague or repeated words that push a feeling instead of informing.",
    spot: "Swap the charged words for neutral ones. Does the sentence still say the same thing?",
  },
  attack_on_reputation: {
    name: "Attacks on people",
    what: "Labels, doubt, hypocrisy or guilt by association aimed at a person or group instead of their argument.",
    spot: "Is the argument answered, or only the person behind it?",
  },
  justification: {
    name: "Appeals instead of evidence",
    what: "Fear, patriotism, values, authority or “everyone agrees” used to make the point.",
    spot: "Look past the appeal: who says so, and what evidence is given?",
  },
  simplification: {
    name: "Oversimplification",
    what: "One cause for a complex event, a chain of consequences taken for granted, or only two options.",
    spot: "Which other causes or options are left out?",
  },
  distraction: {
    name: "Distraction",
    what: "Misrepresenting the other side, changing the subject, or answering with “what about…”.",
    spot: "Does the original question ever get answered?",
  },
  call: {
    name: "Slogans and conversation stoppers",
    what: "Catchy phrases, deadlines or “nothing more to discuss” lines that replace reasoning.",
    spot: "Rewrite the slogan as a plain claim. Is it still supported?",
  },
};

/** Social platforms searched by `pipeline/retrieve/social.py` (`retrieved_by` = platform). */
export const SOCIAL_PLATFORMS: Readonly<Record<string, string>> = {
  x: "X",
  reddit: "Reddit",
  bluesky: "Bluesky",
  mastodon: "Mastodon",
  telegram: "Telegram",
};

export const OUTLET_TYPE_LABELS: Readonly<
  Record<OutletType, { readonly label: string; readonly tone: "neutral" | "teal" | "caution" }>
> = {
  wire_service: { label: "Wire agency", tone: "teal" },
  fact_checker: { label: "Fact-checker", tone: "teal" },
  national: { label: "National outlet", tone: "neutral" },
  local: { label: "Local outlet", tone: "neutral" },
  satire: { label: "Satire / parody", tone: "caution" },
  partisan: { label: "Partisan outlet", tone: "caution" },
  state_affiliated: { label: "State-affiliated", tone: "caution" },
};

export const LANGUAGE_SUPPORT_LABELS: Readonly<
  Record<
    LanguageSupport,
    { readonly badge: string; readonly detail: string; readonly tone: "teal" | "neutral" | "caution" }
  >
> = {
  evaluated: {
    badge: "Evaluated",
    detail: "In our labelled evaluation set.",
    tone: "teal",
  },
  supported: {
    badge: "Supported",
    detail: "Covered by the models but not in the evaluation set: confidence is capped at 85%.",
    tone: "neutral",
  },
  unsupported: {
    badge: "Unsupported",
    detail: "Outside the models' languages: the analysis abstains.",
    tone: "caution",
  },
};

export const ADAPTER_LABELS: Readonly<Record<string, string>> = {
  feeds: "News feeds",
  google_news: "Google News",
  gdelt: "GDELT",
  gemini: "Gemini search",
  fact_check_api: "Fact-check index",
  oxylabs: "Web search",
  oxylabs_news: "News search",
  ...SOCIAL_PLATFORMS,
};

export const SET_LABELS: Readonly<
  Record<string, { readonly label: string; readonly kind: "positive" | "hard_negative" | "negative" }>
> = {
  fact_checker_debunk: { label: "Fact-checker debunks (ClaimReview)", kind: "positive" },
  euvsDisinfo: { label: "EUvsDisinfo documented cases", kind: "positive" },
  viginum_pravda: { label: "VIGINUM Portal Kombat network", kind: "positive" },
  mainstream: { label: "Mainstream straight reporting", kind: "negative" },
  hard_fact_checks: { label: "Hard neg: Fact-checks quoting hoaxes", kind: "hard_negative" },
  hard_wire_copy: { label: "Hard neg: Syndicated wire agency copy", kind: "hard_negative" },
  hard_press_releases: { label: "Hard neg: Institutional press releases", kind: "hard_negative" },
  hard_satire: { label: "Hard neg: Satire & parody", kind: "hard_negative" },
  hard_op_eds: { label: "Hard neg: Opinion columns", kind: "hard_negative" },
  hard_emotional: { label: "Hard neg: Emotional accurate reporting", kind: "hard_negative" },
};

export const EXPLANATION_LANGUAGE_OPTIONS: readonly {
  readonly code: string;
  readonly label: string;
}[] = [
  { code: "", label: "English (default)" },
  { code: "de", label: "German (Deutsch)" },
  { code: "fr", label: "French (Français)" },
  { code: "es", label: "Spanish (Español)" },
  { code: "it", label: "Italian (Italiano)" },
  { code: "nl", label: "Dutch (Nederlands)" },
  { code: "pl", label: "Polish (Polski)" },
  { code: "pt", label: "Portuguese (Português)" },
  { code: "ru", label: "Russian (Русский)" },
  { code: "uk", label: "Ukrainian (Українська)" },
];

const langDisplay =
  typeof Intl !== "undefined" && typeof Intl.DisplayNames !== "undefined"
    ? new Intl.DisplayNames(["en"], { type: "language" })
    : null;

export function languageName(code: string | null | undefined): string {
  if (!code) return "Unknown";
  const normalized = code.trim().toLowerCase();
  if (!normalized) return "Unknown";
  try {
    return langDisplay?.of(normalized) ?? normalized.toUpperCase();
  } catch {
    return normalized.toUpperCase();
  }
}

export function signalLabel(signal: string): string {
  return SIGNAL_LABELS[signal] ?? signal.replace(/_/g, " ");
}

export function networkLabel(knownNetwork: string): string {
  if (knownNetwork === "portal_kombat") {
    return "VIGINUM: Portal Kombat";
  }
  return knownNetwork.replace(/_/g, " ");
}

/** The two families that name persuasion techniques: the paragraph classifier and the rater. */
export function isTechniqueFamily(family: Family): boolean {
  return family === "techniques" || family === "rhetoric";
}

/** Shown where a `rhetoric` item points at our description of the image, not at the author's words. */
export const IN_THE_IMAGE = "In the image (our description)";
const IMAGE_NOTE_PREFIXES = ["[Visual context] ", "[Satire/humour meme] "] as const;

/**
 * Whether a document paragraph is extract's note about an uploaded image
 * (`pipeline/extract/vision.py`): our words describing what the image shows, not its text.
 */
export function isImageNote(paragraph: string | undefined): boolean {
  return paragraph !== undefined && IMAGE_NOTE_PREFIXES.some((prefix) => paragraph.startsWith(prefix));
}
