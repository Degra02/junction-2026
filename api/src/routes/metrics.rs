use axum::{Json, extract::State};
use junction_contracts::ErrorBody;

use super::published;
use crate::{AppState, error::ApiError};

/// Evaluation metrics for the metrics page, as written by the eval harness (`evals/`).
///
/// The shape is owned by the eval harness; the API serves the file unchanged.
#[utoipa::path(
    get,
    path = "/api/metrics",
    tag = "ops",
    responses(
        (status = 200, description = "Eval harness output", body = Object),
        (status = 404, description = "No metrics published yet", body = ErrorBody),
    )
)]
pub async fn metrics(State(state): State<AppState>) -> Result<Json<serde_json::Value>, ApiError> {
    published(&state.config.metrics_path, "no metrics published yet").await
}
