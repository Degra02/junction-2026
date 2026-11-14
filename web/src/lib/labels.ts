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

export const STAGE_LABELS: Readonly<
  Record<StageName, { readonly label: string; readonly activeVerb: string }>
> = {
  extract: {
    label: "Read content & detect language",
    activeVerb: "Reading the content and outlet metadata…",
  },
  understand: {
    label: "Identify key claims & search queries",
    activeVerb: "Locating verbatim claims and building multilingual queries…",
  },
  retrieve: {
    label: "Search live coverage & fact-checkers",
    activeVerb: "Gathering related articles, fact-checks, and domain records…",
  },
  story: {
    label: "Group coverage of the same event",
    activeVerb: "Clustering articles covering the same story…",
  },
  signals_single: {
    label: "Compare content & claims against peers",
    activeVerb: "Checking persuasion techniques, peer tone, and claim support…",
  },
  signals_coordinated: {
    label: "Check cross-outlet coordination",
    activeVerb: "Scanning for copied passages, timing bursts, and shared IDs…",
  },
  score: {
    label: "Combine signal families",
    activeVerb: "Computing family contributions and abstention checks…",
  },
  explain: {
    label: "Write evidence-backed summary",
    activeVerb: "Drafting plain-language reasons with verbatim quote checks…",
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
    shortTitle: "Single-actor manipulation",
    subtitle:
      "Persuasion techniques, emotional intensity relative to story peers, claims contradicted by other reporting or fact-checkers, and outlet profile.",
    families: ["techniques", "tone", "claim_support", "fact_checks", "source_profile"],
  },
  coordinated: {
    title: "Signs of a coordinated campaign",
    shortTitle: "Coordinated amplification",
    subtitle:
      "Near-duplicate passages across unrelated outlets (excluding wire syndication), synchronized timing, shared analytics IDs, and documented networks.",
    families: ["text_reuse", "timing", "infrastructure", "known_networks"],
  },
};

export const FAMILY_LABELS: Readonly<
  Record<Family, { readonly name: string; readonly hint: string; readonly dimension: DimensionKey }>
> = {
  techniques: {
    name: "Persuasion techniques",
    hint: "Share of paragraphs using loaded wording, attacks, fear appeals, or oversimplification",
    dimension: "single",
  },
  tone: {
    name: "Tone vs. story peers",
    hint: "Emotional charge compared with other outlets covering the exact same event",
    dimension: "single",
  },
  claim_support: {
    name: "Claim corroboration",
    hint: "Cross-lingual natural-language inference against peer coverage",
    dimension: "single",
  },
  fact_checks: {
    name: "Fact-checker reviews",
    hint: "Published ClaimReview verdicts matching assertions in the text",
    dimension: "single",
  },
  source_profile: {
    name: "Source & domain profile",
    hint: "Domain registration age, certificate history, and measurable outlet type",
    dimension: "single",
  },
  text_reuse: {
    name: "Copied passages",
    hint: "Unrelated domains publishing the same non-agency passages",
    dimension: "coordinated",
  },
  timing: {
    name: "Publication timing",
    hint: "Copies appearing within a narrow 6-hour window",
    dimension: "coordinated",
  },
  infrastructure: {
    name: "Shared infrastructure",
    hint: "Shared GA / GTM / AdSense IDs or newly registered copying domains",
    dimension: "coordinated",
  },
  known_networks: {
    name: "Documented networks",
    hint: "Presence on VIGINUM's Portal Kombat domain list",
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
    badge: "Evaluated language",
    detail: "Included in our third-party labelled evaluation benchmark.",
    tone: "teal",
  },
  supported: {
    badge: "Supported · uncalibrated tier",
    detail: "Covered by the multilingual models, without dedicated labelled items yet; confidence is capped at 85%.",
    tone: "neutral",
  },
  unsupported: {
    badge: "Unsupported language",
    detail: "Outside the multilingual model set; the pipeline abstains rather than guessing.",
    tone: "caution",
  },
};

export const ADAPTER_LABELS: Readonly<Record<string, string>> = {
  feeds: "Curated RSS",
  google_news: "Google News",
  gdelt: "GDELT",
  gemini: "Gemini Search",
  fact_check_api: "Fact Check API",
  oxylabs: "Oxylabs Web",
  oxylabs_news: "Oxylabs News",
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
