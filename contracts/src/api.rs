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
    /// False until the stage's owner ships its `run` function, or when it failed to load.
    pub implemented: bool,
    /// Why the stage failed to load (exception type); null when it loaded or is not shipped yet.
    pub error: Option<String>,
}

/// Response of `GET /api/stats`: usage and latency over every stored analysis.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct Stats {
    pub analyses: StatusCounts,
    /// Accepted `POST /api/analyses` requests, cache hits included.
    pub submissions: u64,
    /// Submissions answered with an earlier analysis of the same input.
    pub cache_hits: u64,
    /// Wall time of `done` analyses from submission to result, queue wait included.
    pub analysis_ms: Option<Percentiles>,
    /// One entry per stage, in execution order.
    pub stages: Vec<StageStats>,
}

/// Number of analyses per status.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct StatusCounts {
    pub queued: u64,
    pub running: u64,
    pub done: u64,
    pub failed: u64,
}

/// Nearest-rank percentiles in milliseconds.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct Percentiles {
    pub p50: u64,
    pub p95: u64,
}

/// Counts of one stage over the stored analyses. A re-run keeps the steps before its first
/// stage, so those count once per record that carries them.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
pub struct StageStats {
    pub name: StageName,
    pub done: u64,
    pub failed: u64,
    pub skipped: u64,
    /// Duration of the `done` runs; null when there are none.
    pub duration_ms: Option<Percentiles>,
}

/// Payload of the server-sent events on `GET /api/analyses/{id}/events`.
///
/// The SSE event name equals `type`. The stream starts with `snapshot`, sends `queue` while the
/// analysis waits its turn and `step` on every step change (a running step repeats with a new
/// `detail` as the stage reports progress), and ends with `done` (also sent for failed analyses).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum AnalysisEvent {
    #[schema(title = "SnapshotEvent")]
    Snapshot { analysis: Box<Analysis> },
    /// New place in the queue; 1 = next to start.
    #[schema(title = "QueueEvent")]
    Queue { position: u32 },
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
            Self::Queue { .. } => "queue",
            Self::Step { .. } => "step",
            Self::Done { .. } => "done",
        }
    }
}
