use std::{convert::Infallible, fmt::Write as _};

use axum::{
    Json,
    extract::State,
    http::StatusCode,
    response::sse::{Event, KeepAlive, Sse},
};
use chrono::Utc;
use futures_util::{Stream, StreamExt as _, stream};
use junction_contracts::{
    Analysis, AnalysisEvent, AnalysisStatus, Created, ErrorBody, Input, InputKind,
};
use sha2::{Digest as _, Sha256};
use tokio_stream::wrappers::BroadcastStream;
use uuid::Uuid;

use crate::{
    AppState,
    error::{ApiError, ApiJson, ApiPath},
};

/// Longest accepted URL.
const MAX_URL_CHARS: usize = 2048;

/// Start an analysis of pasted text or an article URL.
///
/// Returns at once; follow progress on `/api/analyses/{id}/events`. Re-submitting the same input
/// returns the earlier analysis (`cached: true`) unless that one failed.
#[utoipa::path(
    post,
    path = "/api/analyses",
    tag = "analyses",
    request_body = Input,
    responses(
        (status = 202, description = "Analysis queued or reused", body = Created),
        (status = 422, description = "Invalid input", body = ErrorBody),
        (status = 429, description = "Rate limited", body = ErrorBody),
    )
)]
pub async fn create(
    State(state): State<AppState>,
    ApiJson(input): ApiJson<Input>,
) -> Result<(StatusCode, Json<Created>), ApiError> {
    let input = validate(&input, state.config.max_input_chars)?;
    let hash = input_hash(&input, &state.config.pipeline_version);
    if let Some(id) = state.db.find_reusable(&hash).await? {
        return Ok((StatusCode::ACCEPTED, Json(Created { id, cached: true })));
    }
    let analysis = Analysis::new(
        Uuid::now_v7(),
        input,
        state.config.pipeline_version.clone(),
        Utc::now(),
    );
    state.db.insert(&analysis, &hash).await?;
    let id = analysis.id;
    state.pipeline.spawn(analysis);
    Ok((StatusCode::ACCEPTED, Json(Created { id, cached: false })))
}

/// Read an analysis: progress while running, the full result once done.
#[utoipa::path(
    get,
    path = "/api/analyses/{id}",
    tag = "analyses",
    params(("id" = Uuid, Path, description = "Analysis ID")),
    responses(
        (status = 200, body = Analysis),
        (status = 404, body = ErrorBody),
    )
)]
pub async fn get_one(
    State(state): State<AppState>,
    ApiPath(id): ApiPath<Uuid>,
) -> Result<Json<Analysis>, ApiError> {
    state
        .db
        .get(id)
        .await?
        .map(Json)
        .ok_or_else(|| not_found(id))
}

/// Server-sent progress events.
///
/// Starts with a `snapshot` of the record, then `step` events, and ends with `done`. A finished
/// analysis sends `snapshot` and `done` at once. Clients that fall behind are disconnected and
/// get a fresh snapshot when `EventSource` reconnects. Payloads are `AnalysisEvent`.
#[utoipa::path(
    get,
    path = "/api/analyses/{id}/events",
    tag = "analyses",
    params(("id" = Uuid, Path, description = "Analysis ID")),
    responses(
        (status = 200, description = "Stream of `AnalysisEvent`", content_type = "text/event-stream"),
        (status = 404, body = ErrorBody),
    )
)]
pub async fn events(
    State(state): State<AppState>,
    ApiPath(id): ApiPath<Uuid>,
) -> Result<Sse<impl Stream<Item = Result<Event, Infallible>>>, ApiError> {
    // Subscribe before reading the record so no step between the two is lost.
    let live = state.hub.subscribe(id);
    let analysis = state.db.get(id).await?.ok_or_else(|| not_found(id))?;
    let finished = matches!(
        analysis.status,
        AnalysisStatus::Done | AnalysisStatus::Failed
    );

    let mut first = vec![AnalysisEvent::Snapshot {
        analysis: Box::new(analysis.clone()),
    }];
    let live = match live {
        Some(rx) if !finished => Some(rx),
        _ => {
            first.push(AnalysisEvent::Done {
                analysis: Box::new(analysis),
            });
            None
        }
    };
    let updates = live.map(|rx| {
        // A lagged receiver yields an error: end the stream; the client reconnects.
        BroadcastStream::new(rx)
            .take_while(|m| std::future::ready(m.is_ok()))
            .filter_map(|m| std::future::ready(m.ok()))
    });
    let events = stream::iter(first)
        .chain(stream::iter(updates).flatten())
        .map(|e| Ok(to_sse(&e)))
        .take_until(state.shutdown.cancelled_owned());
    Ok(Sse::new(events).keep_alive(KeepAlive::default()))
}

fn to_sse(event: &AnalysisEvent) -> Event {
    Event::default()
        .event(event.name())
        .json_data(event)
        .unwrap_or_else(|e| Event::default().event("error").data(e.to_string()))
}

fn not_found(id: Uuid) -> ApiError {
    ApiError::NotFound(format!("no analysis with id {id}"))
}

fn validate(input: &Input, max_chars: usize) -> Result<Input, ApiError> {
    let value = input.value.trim().to_owned();
    match input.kind {
        InputKind::Text => {
            let chars = value.chars().count();
            if chars == 0 {
                return Err(ApiError::InvalidInput("the text is empty".into()));
            }
            if chars > max_chars {
                return Err(ApiError::InvalidInput(format!(
                    "the text has {chars} characters; the limit is {max_chars}"
                )));
            }
        }
        InputKind::Url => {
            if value.chars().count() > MAX_URL_CHARS {
                return Err(ApiError::InvalidInput("the URL is too long".into()));
            }
            let url = url::Url::parse(&value)
                .map_err(|e| ApiError::InvalidInput(format!("not a valid URL: {e}")))?;
            if !matches!(url.scheme(), "http" | "https") || url.host_str().is_none() {
                return Err(ApiError::InvalidInput(
                    "only http(s) URLs can be analysed".into(),
                ));
            }
        }
    }
    Ok(Input {
        kind: input.kind,
        value,
    })
}

/// Cache key: pipeline version, input kind and the value with whitespace runs collapsed.
fn input_hash(input: &Input, pipeline_version: &str) -> String {
    let normalized = input.value.split_whitespace().collect::<Vec<_>>().join(" ");
    let kind = match input.kind {
        InputKind::Text => "text",
        InputKind::Url => "url",
    };
    let digest = Sha256::new()
        .chain_update(pipeline_version)
        .chain_update([0])
        .chain_update(kind)
        .chain_update([0])
        .chain_update(normalized)
        .finalize();
    digest.iter().fold(String::with_capacity(64), |mut hex, b| {
        let _ = write!(hex, "{b:02x}");
        hex
    })
}
