use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

use crate::stage::StageName;

/// One analysis of one piece of content. Every stage reads it and returns a patch.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Analysis {
    pub id: Uuid,
    /// [`crate::SCHEMA_VERSION`] at creation time.
    pub schema_version: u32,
    /// Build or model-set identifier; part of the cache key, so a new pipeline re-analyses.
    pub pipeline_version: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub status: AnalysisStatus,
    /// Place in the queue (1 = next to start) while `status` is `queued`; null otherwise.
    pub queue_position: Option<u32>,
    /// Why the analysis failed, in plain language. Set only when `status` is `failed`.
    pub error: Option<String>,
    /// One entry per pipeline stage, in execution order.
    pub steps: Vec<Step>,
    pub input: Input,
    /// Detected language of the input and how well the pipeline supports it (D2). Set by `extract`.
    pub language: Option<Language>,
    /// Cleaned content of the input. Set by `extract`.
    pub document: Option<Document>,
    /// What the item is about. Set by `understand`.
    pub topic: Option<Topic>,
    /// Key claims, each traceable to a verbatim span of the document. Set by `understand`.
    pub claims: Vec<Claim>,
    /// Search queries in the item's language and in English. Set by `understand`.
    pub queries: Vec<SearchQuery>,
    /// Related items found online. Set by `retrieve`; `story` fills the story fields.
    pub context: Vec<ContextItem>,
    /// What is known about the outlets behind the document and the context items, one entry
    /// per domain. Set by `retrieve`.
    pub sources: Vec<SourceProfile>,
    /// Signals with their evidence. Appended by `signals_single` and `signals_coordinated`.
    pub evidence: Vec<Evidence>,
    /// Confidence per dimension. Set by `score`.
    pub scores: Option<Scores>,
    /// Plain-language reasons, each tied to evidence. Set by `explain`.
    pub explanation: Option<Explanation>,
}

impl Analysis {
    /// A queued analysis with every stage pending.
    #[must_use]
    pub fn new(id: Uuid, input: Input, pipeline_version: String, now: DateTime<Utc>) -> Self {
        Self {
            id,
            schema_version: crate::SCHEMA_VERSION,
            pipeline_version,
            created_at: now,
            updated_at: now,
            status: AnalysisStatus::Queued,
            queue_position: None,
            error: None,
            steps: StageName::ALL.into_iter().map(Step::pending).collect(),
            input,
            language: None,
            document: None,
            topic: None,
            claims: vec![],
            queries: vec![],
            context: vec![],
            sources: vec![],
            evidence: vec![],
            scores: None,
            explanation: None,
        }
    }

    /// The step entry of `stage`.
    pub fn step_mut(&mut self, stage: StageName) -> &mut Step {
        self.steps
            .iter_mut()
            .find(|s| s.name == stage)
            .expect("Analysis::new creates one step per stage")
    }

    /// The step entry of `stage`.
    pub fn step(&self, stage: StageName) -> &Step {
        self.steps
            .iter()
            .find(|s| s.name == stage)
            .expect("Analysis::new creates one step per stage")
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum AnalysisStatus {
    Queued,
    Running,
    /// All stages ran; scores are present. Single stages after `score` may still have failed.
    Done,
    /// No usable result: the input could not be read or no score was produced.
    Failed,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Step {
    pub name: StageName,
    pub state: StepState,
    pub duration_ms: Option<u64>,
    /// Short progress note for the UI, e.g. "14 sources" or "2 claims dropped: not verbatim".
    pub detail: Option<String>,
    /// Why the stage failed or was skipped.
    pub error: Option<String>,
}

impl Step {
    /// A stage that has not started.
    #[must_use]
    pub const fn pending(name: StageName) -> Self {
        Self {
            name,
            state: StepState::Pending,
            duration_ms: None,
            detail: None,
            error: None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum StepState {
    Pending,
    Running,
    Done,
    /// Not run: not implemented yet, or a stage it depends on produced nothing.
    Skipped,
    Failed,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct Input {
    pub kind: InputKind,
    /// The pasted text, or the article URL.
    pub value: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum InputKind {
    Text,
    Url,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Language {
    /// ISO 639-1 code, e.g. `it`.
    pub code: String,
    /// Detector confidence in `[0, 1]`.
    pub confidence: f64,
    pub support: LanguageSupport,
}

/// Support tiers shown to the user (D2).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum LanguageSupport {
    /// Present in our labelled sets; calibrated scores.
    Evaluated,
    /// Covered by the models, no labels; confidence is capped.
    Supported,
    /// Not covered; the pipeline abstains.
    Unsupported,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Document {
    /// Source URL when the input was a URL.
    pub url: Option<String>,
    /// Outlet domain, e.g. `example.com`.
    pub outlet: Option<String>,
    pub published_at: Option<DateTime<Utc>>,
    pub title: Option<String>,
    pub author: Option<String>,
    /// Body paragraphs; spans index into these.
    pub paragraphs: Vec<String>,
    pub outbound_links: Vec<String>,
    /// Analytics and ad IDs found in the page (GA, GTM, `AdSense`), e.g. `UA-12345-1`.
    pub tracking_ids: Vec<String>,
}

/// A verbatim slice of `document.paragraphs[paragraph]`.
///
/// Offsets count Unicode code points (Python `str` indexing), `end` exclusive. JavaScript
/// strings index UTF-16 code units: slice with `Array.from(paragraph).slice(start, end)`,
/// otherwise spans after an emoji are off.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct Span {
    pub paragraph: u32,
    pub start: u32,
    pub end: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Topic {
    pub summary: String,
    pub entities: Vec<String>,
    /// Event date as written or normalised (free text, e.g. `2026-11-12`).
    pub date: Option<String>,
    pub place: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Claim {
    /// Unique within the analysis, e.g. `cl1`.
    pub id: String,
    /// Must equal the document text at `span`, otherwise the claim is dropped.
    pub text: String,
    pub span: Span,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct SearchQuery {
    pub text: String,
    /// ISO 639-1 code of the query.
    pub language: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct ContextItem {
    /// Unique within the analysis, e.g. `ctx1`.
    pub id: String,
    pub url: String,
    pub outlet: Option<String>,
    pub published_at: Option<DateTime<Utc>>,
    pub title: Option<String>,
    /// Extracted body text; quotes in evidence must be substrings of it. For a fact-check: the
    /// reviewed claim followed by the verdict text.
    pub text: String,
    /// ISO 639-1 code.
    pub language: Option<String>,
    /// Adapter that found it, e.g. `google_news`, `gdelt`, `fact_check_api`, `oxylabs`.
    pub retrieved_by: String,
    /// Analytics and ad IDs found in the page (GA, GTM, `AdSense`); compared across outlets by
    /// the infrastructure signal. Empty when the page was not fetched.
    pub tracking_ids: Vec<String>,
    /// Set when the item is a fact-check (`ClaimReview`) rather than coverage of the event.
    pub fact_check: Option<FactCheck>,
    /// Similarity to the analysed item. Set by `story`.
    pub similarity: Option<f64>,
    /// Whether it covers the same event. Set by `story`.
    pub in_story: Option<bool>,
    /// Why it was kept or dropped from the story. Set by `story`.
    pub story_reason: Option<String>,
}

/// A published fact-check of a claim (`ClaimReview`, e.g. from the Google Fact Check Tools API).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct FactCheck {
    /// The claim that was reviewed, as stated by the fact-checker.
    pub claim: String,
    /// Textual rating as published, e.g. `False`, `Misleading`, `Mostly true`.
    pub rating: String,
    /// Fact-checking organisation, e.g. `Pagella Politica`.
    pub publisher: Option<String>,
}

/// Measurable facts about one outlet (D9: no political-bias ratings).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct SourceProfile {
    /// Outlet domain as written in `document.outlet` and `context[].outlet`; unique in `sources`.
    pub domain: String,
    /// Domain registration date (RDAP).
    pub registered_at: Option<DateTime<Utc>>,
    /// Issue date of the first certificate in the Certificate Transparency logs.
    pub first_cert_at: Option<DateTime<Utc>>,
    pub outlet_type: Option<OutletType>,
    /// ISO 3166-1 alpha-2 country of the outlet, e.g. `IT`.
    pub country: Option<String>,
    /// Documented network that lists the domain, e.g. `portal_kombat` (VIGINUM); null when
    /// it is on no list.
    pub known_network: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum OutletType {
    /// News agency whose copy is syndicated (Reuters, AP, AFP, dpa, EFE, ANSA): reuse of its
    /// text is not coordination.
    WireService,
    National,
    Local,
    Partisan,
    StateAffiliated,
    FactChecker,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum Dimension {
    /// Manipulation by the author.
    Single,
    /// The same message pushed by many outlets acting together.
    Coordinated,
}

/// Signal family; inside a family only the strongest signal counts (plan §5).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum Family {
    Techniques,
    Tone,
    ClaimSupport,
    FactChecks,
    SourceProfile,
    TextReuse,
    Timing,
    Infrastructure,
    KnownNetworks,
}

impl Family {
    #[must_use]
    pub const fn dimension(self) -> Dimension {
        match self {
            Self::Techniques
            | Self::Tone
            | Self::ClaimSupport
            | Self::FactChecks
            | Self::SourceProfile => Dimension::Single,
            Self::TextReuse | Self::Timing | Self::Infrastructure | Self::KnownNetworks => {
                Dimension::Coordinated
            }
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Evidence {
    /// Unique within the analysis. Use a stage prefix (`s1`, `c1`) to avoid clashes.
    pub id: String,
    pub family: Family,
    /// Signal name inside the family, e.g. `loaded_language`, `minhash_copies`.
    pub signal: String,
    /// Signal value; scale is defined per signal and documented by its owner.
    pub value: f64,
    /// One plain-language sentence for the UI.
    pub detail: String,
    /// Where the evidence comes from: at least one. Items without a source, or with a dangling
    /// or non-verbatim ref, are dropped.
    pub source_refs: Vec<SourceRef>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum SourceRef {
    /// A span of the analysed document.
    #[schema(title = "DocumentRef")]
    Document { span: Span },
    /// A retrieved context item, optionally with a quote that must appear verbatim in its text.
    #[schema(title = "ContextRef")]
    Context { id: String, quote: Option<String> },
    /// An external source that is not a context item, e.g. a fact-check or RDAP record.
    #[schema(title = "UrlRef")]
    Url { url: String },
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Scores {
    pub single: Score,
    pub coordinated: Score,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Score {
    /// Calibrated confidence in `[0, 1]`; null when abstained.
    pub confidence: Option<f64>,
    /// True shows "Not enough evidence" instead of a score.
    pub abstained: bool,
    /// Why it abstained. Required when `abstained`.
    pub reason: Option<String>,
    /// Contribution of each family, the weights shown to the user.
    pub breakdown: Vec<Contribution>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Contribution {
    pub family: Family,
    /// Log-odds contribution of the family (combiner coefficient × value).
    pub contribution: f64,
    pub evidence_ids: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Explanation {
    /// Blanked when it contains a quotation that is not verbatim in the analysed material.
    pub summary: String,
    /// Each reason must cite at least one existing evidence ID and quote only verbatim text
    /// (document, context items, evidence details), otherwise it is dropped. A quotation is a
    /// passage of 12 or more characters inside double quotes or guillemets.
    pub reasons: Vec<Reason>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
pub struct Reason {
    pub text: String,
    pub evidence_ids: Vec<String>,
}
