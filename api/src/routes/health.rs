use axum::{Json, extract::State};
use junction_contracts::{ErrorBody, Health};

use crate::{AppState, error::ApiError};

/// API, database and worker status.
///
/// 200 while the API and its database work, even if the worker is down (`worker: null`), so a
/// worker restart does not take the API out of the load balancer.
#[utoipa::path(
    get,
    path = "/api/health",
    tag = "ops",
    responses(
        (status = 200, body = Health),
        (status = 503, description = "Database unavailable", body = ErrorBody),
    )
)]
pub async fn health(State(state): State<AppState>) -> Result<Json<Health>, ApiError> {
    state
        .db
        .ping()
        .await
        .map_err(|e| ApiError::Unavailable(format!("database: {e}")))?;
    Ok(Json(Health {
        status: "ok".into(),
        pipeline_version: state.config.pipeline_version.clone(),
        worker: state.worker.health().await,
    }))
}
