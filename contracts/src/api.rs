use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

use crate::analysis::{Analysis, Step};
use crate::stage::StageName;

/// Response of `POST /api/analyses`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct Created {
    pub id: Uuid,
    /// True when an earlier analysis of the same input and pipeline version was reused.
    pub cached: bool,
}

/// Error body of every non-2xx JSON response.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct ErrorBody {
    /// Stable machine-readable code, e.g. `invalid_input`, `not_found`, `rate_limited`.
    pub error: String,
    /// Human-readable explanation.
    pub message: String,
}

/// Response of `GET /api/health`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct Health {
    /// `ok` when the API and its database work.
    pub status: String,
    pub pipeline_version: String,
    /// Null when the worker is unreachable.
    pub worker: Option<WorkerHealth>,
}

/// Response of the worker's `GET /health`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct WorkerHealth {
    pub stages: Vec<StageAvailability>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct StageAvailability {
    pub name: StageName,
    /// False until the stage's owner ships its `run` function.
    pub implemented: bool,
}

/// Payload of the server-sent events on `GET /api/analyses/{id}/events`.
///
/// The SSE event name equals `type`. The stream starts with `snapshot`, sends `step` on every
/// step change and ends with `done` (also sent for failed analyses).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum AnalysisEvent {
    #[schema(title = "SnapshotEvent")]
    Snapshot { analysis: Box<Analysis> },
    #[schema(title = "StepEvent")]
    Step { step: Step },
    #[schema(title = "DoneEvent")]
    Done { analysis: Box<Analysis> },
}

impl AnalysisEvent {
    #[must_use]
    pub const fn name(&self) -> &'static str {
        match self {
            Self::Snapshot { .. } => "snapshot",
            Self::Step { .. } => "step",
            Self::Done { .. } => "done",
        }
    }
}
