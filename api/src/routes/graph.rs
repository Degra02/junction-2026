use axum::{Json, extract::State};
use junction_contracts::ErrorBody;

use super::published;
use crate::{AppState, error::ApiError};

/// The source graph: outlets tied by shared analytics IDs, copied text, translations and links.
///
/// Built offline from stored analyses (`mise run graph:build`). The shape is owned by
/// `pipeline/graph/build.py`; the API serves the file unchanged. A tie is evidence of a
/// relationship between two sites, not a judgement of either.
#[utoipa::path(
    get,
    path = "/api/graph",
    tag = "sources",
    responses(
        (status = 200, description = "Outlets, ties with their evidence, clusters", body = Object),
        (status = 404, description = "No source graph published yet", body = ErrorBody),
    )
)]
pub async fn graph(State(state): State<AppState>) -> Result<Json<serde_json::Value>, ApiError> {
    published(&state.config.graph_path, "no source graph published yet").await
}
