use std::{convert::Infallible, fmt::Write as _, net::Ipv4Addr, time::Duration};

use axum::{
    Json,
    extract::State,
    http::StatusCode,
    response::sse::{Event, KeepAlive, Sse},
};
use chrono::Utc;
use futures_util::{
    Stream, StreamExt as _,
    stream::{self, BoxStream},
};
use junction_contracts::{
    Analysis, AnalysisEvent, AnalysisStatus, Created, ErrorBody, Input, InputKind, StageName, Step,
    StepState,
};
use serde::Deserialize;
use sha2::{Digest as _, Sha256};
use tokio_stream::wrappers::BroadcastStream;
use utoipa::IntoParams;
use uuid::Uuid;

use crate::{
    AppState,
    error::{ApiError, ApiJson, ApiPath, ApiQuery},
    pipeline::rerun_record,
    ratelimit::ClientIp,
};

/// Longest accepted URL.
const MAX_URL_CHARS: usize = 2048;
/// Replay: pause before a step starts, and the bounds of the time it then appears to run.
const REPLAY_GAP: Duration = Duration::from_millis(100);
const REPLAY_STEP_MS: (u64, u64) = (200, 1500);

#[derive(Debug, Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct CreateParams {
    /// Run again even when an earlier analysis of the same input could be reused.
    #[serde(default)]
    force: bool,
}

/// Start an analysis of pasted text or an article URL.
///
/// Returns at once; follow progress on `/api/analyses/{id}/events`. Re-submitting the same input
/// returns the earlier analysis (`cached: true`) unless that one failed, had a failed step, or
/// `force=true` is set. Only new analyses count towards the rate limits.
#[utoipa::path(
    post,
    path = "/api/analyses",
    tag = "analyses",
    params(CreateParams),
    request_body = Input,
    responses(
        (status = 202, description = "Analysis queued or reused", body = Created),
        (status = 422, description = "Invalid input", body = ErrorBody),
        (status = 429, description = "Rate limited (`rate_limited` per client, `busy` service-wide)", body = ErrorBody),
    )
)]
pub async fn create(
    State(state): State<AppState>,
    ClientIp(client): ClientIp,
    ApiQuery(params): ApiQuery<CreateParams>,
    ApiJson(input): ApiJson<Input>,
) -> Result<(StatusCode, Json<Created>), ApiError> {
    let input = validate(&input, state.config.max_input_chars)?;
    let hash = input_hash(&input, &state.config.pipeline_version);

    let _one_at_a_time = state.create_lock.lock().await;
    if !params.force
        && let Some(id) = state.db.find_reusable(&hash).await?
    {
        state.db.count_submission(true).await?;
        return Ok((StatusCode::ACCEPTED, Json(Created { id, cached: true })));
    }
    state.rate_limiter.check(client)?;
    let analysis = Analysis::new(
        Uuid::now_v7(),
        input,
        state.config.pipeline_version.clone(),
        Utc::now(),
    );
    start(&state, analysis, &hash).await
}

#[derive(Debug, Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct RerunParams {
    /// First stage to run again.
    from: StageName,
}

/// Run a finished analysis again from one stage on.
///
/// Creates a new analysis that keeps the stored output of the stages before `from` and runs
/// `from` and everything after it (both signal stages when `from` is either of them). Use it to
/// retry a stage that failed, or to score the same retrieved context again after a change to
/// the signals, the combiner or the explanation. The new analysis replaces the source as the
/// cached result of its input.
#[utoipa::path(
    post,
    path = "/api/analyses/{id}/rerun",
    tag = "analyses",
    params(("id" = Uuid, Path, description = "Analysis to start from"), RerunParams),
    responses(
        (status = 202, description = "New analysis queued", body = Created),
        (status = 404, body = ErrorBody),
        (status = 409, description = "The source analysis has not finished", body = ErrorBody),
        (status = 422, description = "Unknown stage", body = ErrorBody),
        (status = 429, description = "Rate limited", body = ErrorBody),
    )
)]
pub async fn rerun(
    State(state): State<AppState>,
    ClientIp(client): ClientIp,
    ApiPath(id): ApiPath<Uuid>,
    ApiQuery(params): ApiQuery<RerunParams>,
) -> Result<(StatusCode, Json<Created>), ApiError> {
    let source = state.db.get(id).await?.ok_or_else(|| not_found(id))?;
    if !is_finished(&source) {
        return Err(ApiError::Conflict(
            "the analysis is still running; run it again once it has finished".into(),
        ));
    }
    state.rate_limiter.check(client)?;
    let version = state.config.pipeline_version.clone();
    let hash = input_hash(&source.input, &version);
    let analysis = rerun_record(source, params.from, Uuid::now_v7(), version, Utc::now());
    start(&state, analysis, &hash).await
}

/// Persists a queued analysis and hands it to the pipeline.
async fn start(
    state: &AppState,
    analysis: Analysis,
    hash: &str,
) -> Result<(StatusCode, Json<Created>), ApiError> {
    state.db.insert(&analysis, hash).await?;
    state.db.count_submission(false).await?;
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
    load(&state, id).await.map(Json)
}

/// The stored record with its current place in the queue.
async fn load(state: &AppState, id: Uuid) -> Result<Analysis, ApiError> {
    let mut analysis = state.db.get(id).await?.ok_or_else(|| not_found(id))?;
    analysis.queue_position = state.pipeline.queue_position(id);
    Ok(analysis)
}

#[derive(Debug, Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct EventsParams {
    /// For a finished analysis: send its steps again with short pauses, as if it ran now.
    #[serde(default)]
    replay: bool,
}

/// Server-sent progress events.
///
/// Starts with a `snapshot` of the record, then `queue` and `step` events, and ends with `done`.
/// A finished analysis sends `snapshot` and `done` at once, or with `replay=true` plays its
/// stored steps back from an empty snapshot (a demo that does not depend on live sources).
/// Clients that fall behind are disconnected and get a fresh snapshot when `EventSource`
/// reconnects. Payloads are `AnalysisEvent`.
#[utoipa::path(
    get,
    path = "/api/analyses/{id}/events",
    tag = "analyses",
    params(("id" = Uuid, Path, description = "Analysis ID"), EventsParams),
    responses(
        (status = 200, description = "Stream of `AnalysisEvent`", content_type = "text/event-stream"),
        (status = 404, body = ErrorBody),
    )
)]
pub async fn events(
    State(state): State<AppState>,
    ApiPath(id): ApiPath<Uuid>,
    ApiQuery(params): ApiQuery<EventsParams>,
) -> Result<Sse<impl Stream<Item = Result<Event, Infallible>>>, ApiError> {
    // Subscribe before reading the record so no step between the two is lost.
    let live = state.hub.subscribe(id);
    let analysis = load(&state, id).await?;

    let events: BoxStream<'static, AnalysisEvent> = if is_finished(&analysis) {
        if params.replay {
            replay(analysis).boxed()
        } else {
            let snapshot = AnalysisEvent::Snapshot {
                analysis: Box::new(analysis.clone()),
            };
            let done = AnalysisEvent::Done {
                analysis: Box::new(analysis),
            };
            stream::iter([snapshot, done]).boxed()
        }
    } else {
        let snapshot = AnalysisEvent::Snapshot {
            analysis: Box::new(analysis),
        };
        let updates = live.map(|rx| {
            // A lagged receiver yields an error: end the stream; the client reconnects.
            BroadcastStream::new(rx)
                .take_while(|m| std::future::ready(m.is_ok()))
                .filter_map(|m| std::future::ready(m.ok()))
        });
        stream::iter([snapshot])
            .chain(stream::iter(updates).flatten())
            .boxed()
    };
    let events = events
        .map(|e| Ok(to_sse(&e)))
        .take_until(state.shutdown.cancelled_owned())
        .boxed();
    Ok(Sse::new(events).keep_alive(KeepAlive::default()))
}

/// The events a finished analysis produced, re-timed: a snapshot without results, each step
/// running and then in its stored final state, and the full record at the end.
fn replay(analysis: Analysis) -> impl Stream<Item = AnalysisEvent> + Send {
    let mut blank = analysis.clone();
    blank.status = AnalysisStatus::Running;
    blank.error = None;
    for stage in StageName::ALL {
        blank.clear_output(stage);
        *blank.step_mut(stage) = Step::pending(stage);
    }
    let mut timeline = vec![(
        Duration::ZERO,
        AnalysisEvent::Snapshot {
            analysis: Box::new(blank),
        },
    )];
    for step in &analysis.steps {
        // A skipped stage never ran: it only shows its final state.
        if step.state == StepState::Skipped {
            timeline.push((REPLAY_GAP, AnalysisEvent::Step { step: step.clone() }));
            continue;
        }
        let running = Step {
            state: StepState::Running,
            ..Step::pending(step.name)
        };
        timeline.push((REPLAY_GAP, AnalysisEvent::Step { step: running }));
        let ms = step.duration_ms.unwrap_or(0) / 20;
        let shown = Duration::from_millis(ms.clamp(REPLAY_STEP_MS.0, REPLAY_STEP_MS.1));
        timeline.push((shown, AnalysisEvent::Step { step: step.clone() }));
    }
    timeline.push((
        REPLAY_GAP,
        AnalysisEvent::Done {
            analysis: Box::new(analysis),
        },
    ));
    stream::iter(timeline).then(|(pause, event)| async move {
        tokio::time::sleep(pause).await;
        event
    })
}

fn to_sse(event: &AnalysisEvent) -> Event {
    Event::default()
        .event(event.name())
        .json_data(event)
        .unwrap_or_else(|e| Event::default().event("error").data(e.to_string()))
}

const fn is_finished(analysis: &Analysis) -> bool {
    matches!(
        analysis.status,
        AnalysisStatus::Done | AnalysisStatus::Failed
    )
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
            if !matches!(url.scheme(), "http" | "https") {
                return Err(ApiError::InvalidInput(
                    "only http(s) URLs can be analysed".into(),
                ));
            }
            // The worker fetches this URL from inside our network: never let it reach the
            // worker itself, the VPS or a private network. The fetcher repeats the check on
            // the resolved address (`pipeline.common.net`).
            if !is_public_host(&url) || url.port().is_some() {
                return Err(ApiError::InvalidInput(
                    "the URL must point to a public website on the default port".into(),
                ));
            }
        }
    }
    Ok(Input {
        kind: input.kind,
        value,
        explanation_language: explanation_language(input.explanation_language.as_deref())?,
    })
}

/// The language code's primary subtag, lowercased (`pt-BR` → `pt`); blank means English (None).
fn explanation_language(asked: Option<&str>) -> Result<Option<String>, ApiError> {
    let Some(asked) = asked.map(str::trim).filter(|s| !s.is_empty()) else {
        return Ok(None);
    };
    let primary = asked.split(['-', '_']).next().unwrap_or_default();
    if !(2..=3).contains(&primary.len()) || !primary.bytes().all(|b| b.is_ascii_alphabetic()) {
        return Err(ApiError::InvalidInput(
            "explanation_language must be a language code such as `it` or `pt-BR`".into(),
        ));
    }
    Ok(Some(primary.to_ascii_lowercase()))
}

/// False for hosts that can only be inside a private network: single-label names (`worker`,
/// `localhost`), internal top-level domains and non-global IP addresses.
fn is_public_host(url: &url::Url) -> bool {
    match url.host() {
        Some(url::Host::Domain(name)) => {
            let name = name.trim_end_matches('.').to_ascii_lowercase();
            name.rsplit_once('.').is_some_and(|(_, tld)| {
                !matches!(
                    tld,
                    "localhost" | "local" | "internal" | "lan" | "home" | "arpa"
                )
            })
        }
        Some(url::Host::Ipv4(ip)) => is_public_v4(ip),
        Some(url::Host::Ipv6(ip)) => ip.to_ipv4_mapped().map_or_else(
            || {
                !(ip.is_loopback()
                    || ip.is_unspecified()
                    || ip.is_multicast()
                    || ip.is_unique_local()
                    || ip.is_unicast_link_local())
            },
            is_public_v4,
        ),
        None => false,
    }
}

fn is_public_v4(ip: Ipv4Addr) -> bool {
    let [a, b, ..] = ip.octets();
    let carrier_nat = a == 100 && b & 0xC0 == 64;
    !(a == 0
        || carrier_nat
        || ip.is_private()
        || ip.is_loopback()
        || ip.is_link_local()
        || ip.is_broadcast()
        || ip.is_multicast())
}

/// Cache key: pipeline version, input kind, the value with whitespace runs collapsed and the
/// explanation language (English when none was asked for).
fn input_hash(input: &Input, pipeline_version: &str) -> String {
    let normalized = input.value.split_whitespace().collect::<Vec<_>>().join(" ");
    let kind = match input.kind {
        InputKind::Text => "text",
        InputKind::Url => "url",
    };
    let language = input.explanation_language.as_deref().unwrap_or("en");
    let digest = Sha256::new()
        .chain_update(pipeline_version)
        .chain_update([0])
        .chain_update(kind)
        .chain_update([0])
        .chain_update(normalized)
        .chain_update([0])
        .chain_update(language)
        .finalize();
    digest.iter().fold(String::with_capacity(64), |mut hex, b| {
        let _ = write!(hex, "{b:02x}");
        hex
    })
}
