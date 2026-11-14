use anyhow::Context as _;
use axum::{Json, extract::State};
use junction_contracts::ErrorBody;

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
    let path = &state.config.metrics_path;
    let bytes = match tokio::fs::read(path).await {
        Ok(b) => b,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            return Err(ApiError::NotFound("no metrics published yet".into()));
        }
        Err(e) => {
            return Err(anyhow::Error::from(e)
                .context(format!("reading {}", path.display()))
                .into());
        }
    };
    let value = serde_json::from_slice(&bytes)
        .with_context(|| format!("{} is not valid JSON", path.display()))?;
    Ok(Json(value))
}
