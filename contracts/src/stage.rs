use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

use crate::analysis::{
    Claim, ContextItem, Dimension, Document, Evidence, Explanation, Language, OutletType, Scores,
    SearchQuery, SourceProfile, Topic,
};

/// Pipeline stage. The worker serves each one at `POST /stages/{name}`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum StageName {
    Extract,
    Understand,
    Retrieve,
    Story,
    SignalsSingle,
    SignalsCoordinated,
    Score,
    Explain,
    Graph,
}

impl StageName {
    /// Execution order; `signals_single` and `signals_coordinated` run in parallel, as do
    /// `explain` and `graph`.
    pub const ALL: [Self; 9] = [
        Self::Extract,
        Self::Understand,
        Self::Retrieve,
        Self::Story,
        Self::SignalsSingle,
        Self::SignalsCoordinated,
        Self::Score,
        Self::Explain,
        Self::Graph,
    ];

    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Extract => "extract",
            Self::Understand => "understand",
            Self::Retrieve => "retrieve",
            Self::Story => "story",
            Self::SignalsSingle => "signals_single",
            Self::SignalsCoordinated => "signals_coordinated",
            Self::Score => "score",
            Self::Explain => "explain",
            Self::Graph => "graph",
        }
    }
}

impl std::fmt::Display for StageName {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

impl std::str::FromStr for StageName {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        Self::ALL
            .into_iter()
            .find(|stage| stage.as_str() == s)
            .ok_or_else(|| format!("unknown stage `{s}`"))
    }
}

/// Response of `POST /stages/extract`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ExtractPatch {
    pub document: Document,
    pub language: Option<Language>,
}

/// Response of `POST /stages/understand`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UnderstandPatch {
    pub topic: Topic,
    pub claims: Vec<Claim>,
    pub queries: Vec<SearchQuery>,
}

/// Response of `POST /stages/retrieve`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct RetrievePatch {
    pub context: Vec<ContextItem>,
    /// Profiles of the outlets seen in the document and the context, one per domain.
    pub sources: Vec<SourceProfile>,
    /// Progress note, e.g. "14 sources from 3 adapters".
    pub detail: Option<String>,
}

/// Response of `POST /stages/story`: story fields for existing context items.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct StoryPatch {
    pub assignments: Vec<StoryAssignment>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct StoryAssignment {
    pub context_id: String,
    pub similarity: f64,
    pub in_story: bool,
    pub reason: Option<String>,
}

/// Response of `POST /stages/signals_single` and `POST /stages/signals_coordinated`.
///
/// Every evidence family must belong to the stage's dimension.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SignalsPatch {
    pub evidence: Vec<Evidence>,
}

/// Response of `POST /stages/score`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ScorePatch {
    pub scores: Scores,
}

/// Response of `POST /stages/explain`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ExplainPatch {
    pub explanation: Explanation,
}

/// Response of `POST /stages/graph`: outlets, articles, tracking IDs and within-record ties.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct GraphPatch {
    pub outlets: Vec<GraphPatchOutlet>,
    pub articles: Vec<GraphPatchArticle>,
    pub ties: Vec<GraphObservation>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct GraphPatchOutlet {
    pub domain: String,
    pub operator: String,
    #[serde(default)]
    pub outlet_type: Option<OutletType>,
    #[serde(default)]
    pub country: Option<String>,
    #[serde(default)]
    pub known_network: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct GraphPatchArticle {
    pub url: String,
    pub outlet: String,
    #[serde(default)]
    pub title: Option<String>,
    #[serde(default)]
    pub published_at: Option<DateTime<Utc>>,
    #[serde(default)]
    pub language: Option<String>,
    #[serde(default)]
    pub analysed: bool,
    #[serde(default)]
    pub fact_check: bool,
    #[serde(default)]
    pub tracking_ids: Vec<String>,
    #[serde(default)]
    pub outbound_domains: Vec<String>,
    /// Unit-length 384-d `story_text` embedding (`multilingual-e5-small`).
    #[serde(default)]
    pub embedding: Vec<f32>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct GraphObservation {
    /// Ordered pair `a < b`.
    pub a: String,
    pub b: String,
    /// Layer kind: `analytics_id`, `ad_account`, `copy`, `translation` or `link`.
    pub kind: String,
    /// Distinct witness keys on side `a` (article URLs or tracking IDs).
    pub keys_a: Vec<String>,
    /// Distinct witness keys on side `b`.
    pub keys_b: Vec<String>,
    /// Evidence items matching `evals/graph.json`.
    pub evidence: Vec<serde_json::Value>,
}

/// A stage result, typed by the stage that produced it.
#[derive(Debug, Clone, PartialEq)]
pub enum StagePatch {
    Extract(ExtractPatch),
    Understand(UnderstandPatch),
    Retrieve(RetrievePatch),
    Story(StoryPatch),
    Signals(Dimension, SignalsPatch),
    Score(ScorePatch),
    Explain(ExplainPatch),
    Graph(GraphPatch),
}

impl StagePatch {
    /// Parses a worker response for `stage`.
    pub fn from_json(stage: StageName, body: &[u8]) -> Result<Self, serde_json::Error> {
        Ok(match stage {
            StageName::Extract => Self::Extract(serde_json::from_slice(body)?),
            StageName::Understand => Self::Understand(serde_json::from_slice(body)?),
            StageName::Retrieve => Self::Retrieve(serde_json::from_slice(body)?),
            StageName::Story => Self::Story(serde_json::from_slice(body)?),
            StageName::SignalsSingle => {
                Self::Signals(Dimension::Single, serde_json::from_slice(body)?)
            }
            StageName::SignalsCoordinated => {
                Self::Signals(Dimension::Coordinated, serde_json::from_slice(body)?)
            }
            StageName::Score => Self::Score(serde_json::from_slice(body)?),
            StageName::Explain => Self::Explain(serde_json::from_slice(body)?),
            StageName::Graph => Self::Graph(serde_json::from_slice(body)?),
        })
    }
}
