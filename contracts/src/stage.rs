use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

use crate::analysis::{
    Claim, ContextItem, Dimension, Document, Evidence, Explanation, Language, Scores, SearchQuery,
    SourceProfile, Topic,
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
}

impl StageName {
    /// Execution order; `signals_single` and `signals_coordinated` run in parallel.
    pub const ALL: [Self; 8] = [
        Self::Extract,
        Self::Understand,
        Self::Retrieve,
        Self::Story,
        Self::SignalsSingle,
        Self::SignalsCoordinated,
        Self::Score,
        Self::Explain,
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
        })
    }
}
