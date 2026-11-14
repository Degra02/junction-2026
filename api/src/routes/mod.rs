//! HTTP routes and the OpenAPI document generated from them.

mod analyses;
mod graph;
mod health;
mod metrics;
mod stats;

use std::{path::Path, time::Duration};

use anyhow::Context as _;
use axum::{Json, Router, http::StatusCode, routing::get};
use junction_contracts as c;
use tower_http::{
    limit::RequestBodyLimitLayer,
    request_id::{MakeRequestUuid, PropagateRequestIdLayer, SetRequestIdLayer},
    timeout::TimeoutLayer,
    trace::TraceLayer,
};
use utoipa::OpenApi;
use utoipa_axum::{router::OpenApiRouter, routes};
use utoipa_scalar::{Scalar, Servable as _};

use crate::{AppState, error::ApiError};

/// Request bodies above this are rejected before parsing (50 000 chars of UTF-8 fit easily).
const MAX_BODY_BYTES: usize = 512 * 1024;

#[derive(OpenApi)]
#[openapi(
    info(
        title = "Junction 2026 propaganda analysis API",
        description = "Submit text or an article URL, follow progress over SSE, read the evidence-backed scores. \
                       Stage patch schemas describe the internal worker API (`POST /stages/{name}`)."
    ),
    components(schemas(
        c::AnalysisEvent,
        c::WorkerHealth,
        c::ExtractPatch,
        c::UnderstandPatch,
        c::RetrievePatch,
        c::StoryPatch,
        c::SignalsPatch,
        c::ScorePatch,
        c::ExplainPatch,
    )),
    tags(
        (name = "analyses", description = "Create and read analyses"),
        (name = "ops", description = "Health, usage and evaluation metrics"),
        (name = "sources", description = "What stored analyses show about the outlets"),
    )
)]
struct ApiDoc;

/// Routes with their OpenAPI metadata; state is attached in [`router`].
fn documented() -> OpenApiRouter<AppState> {
    OpenApiRouter::with_openapi(ApiDoc::openapi())
        .routes(routes!(analyses::create))
        .routes(routes!(analyses::get_one))
        .routes(routes!(analyses::rerun))
        .routes(routes!(analyses::events))
        .routes(routes!(health::health))
        .routes(routes!(stats::stats))
        .routes(routes!(metrics::metrics))
        .routes(routes!(graph::graph))
}

/// A JSON file built offline and shipped with the API, served unchanged; 404 with `missing`
/// until it exists.
async fn published(path: &Path, missing: &str) -> Result<Json<serde_json::Value>, ApiError> {
    let bytes = match tokio::fs::read(path).await {
        Ok(b) => b,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            return Err(ApiError::NotFound(missing.into()));
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

/// The OpenAPI document, as written to `contracts/openapi.json`.
#[must_use]
pub fn openapi() -> utoipa::openapi::OpenApi {
    documented().split_for_parts().1
}

pub fn router(state: AppState) -> Router {
    let (api, spec) = documented().split_for_parts();
    let spec_json = spec.clone();

    api.route(
        "/api/openapi.json",
        get(move || async move { Json(spec_json) }),
    )
    .merge(Scalar::with_url("/api/docs", spec))
    .fallback(|| async {
        (
            StatusCode::NOT_FOUND,
            Json(c::ErrorBody {
                error: "not_found".into(),
                message: "no such route".into(),
            }),
        )
    })
    .with_state(state)
    .layer(RequestBodyLimitLayer::new(MAX_BODY_BYTES))
    .layer(TimeoutLayer::with_status_code(
        StatusCode::REQUEST_TIMEOUT,
        Duration::from_secs(30),
    ))
    .layer(PropagateRequestIdLayer::x_request_id())
    .layer(TraceLayer::new_for_http())
    .layer(SetRequestIdLayer::x_request_id(MakeRequestUuid))
}
