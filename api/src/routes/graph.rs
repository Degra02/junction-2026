use axum::{Json, extract::State};
use junction_contracts::ErrorBody;

use crate::{
    AppState,
    error::{ApiError, ApiPath},
    graph::{build_graph, build_outlet_detail},
};

/// The source graph: outlets tied by shared analytics IDs, copied text, translations and links.
///
/// Assembled live from SQLite (`0003_graph.sql`), merged idempotently with any baseline
/// `evals/graph.json`. Keeps the exact shape of `pipeline/graph/build.py`. A tie is evidence of a
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
    let payload = build_graph(state.db.pool(), &state.config.graph_path).await?;
    payload
        .map(Json)
        .ok_or_else(|| ApiError::NotFound("no source graph published yet".into()))
}

/// One outlet's profile, cluster and ties in the source graph.
#[utoipa::path(
    get,
    path = "/api/graph/outlets/{domain}",
    tag = "sources",
    params(("domain" = String, Path, description = "Outlet domain, e.g. `kxan.com`")),
    responses(
        (status = 200, description = "Outlet profile, cluster and ties", body = Object),
        (status = 404, description = "Outlet not present in the source graph", body = ErrorBody),
    )
)]
pub async fn outlet(
    State(state): State<AppState>,
    ApiPath(domain): ApiPath<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let payload = build_outlet_detail(state.db.pool(), &state.config.graph_path, &domain).await?;
    payload
        .map(Json)
        .ok_or_else(|| ApiError::NotFound(format!("no outlet `{domain}` in the source graph")))
}
