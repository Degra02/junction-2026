use axum::{Json, extract::State};
use chrono::DateTime;
use junction_contracts::{Percentiles, StageName, StageStats, Stats, StatusCounts, StepState};

use crate::{AppState, error::ApiError};

/// Usage and latency over every stored analysis.
///
/// Feeds the "scale" part of the metrics page: how many analyses ran, how often the cache
/// answered, and how long each stage takes on this machine.
#[utoipa::path(
    get,
    path = "/api/stats",
    tag = "ops",
    responses((status = 200, body = Stats))
)]
pub async fn stats(State(state): State<AppState>) -> Result<Json<Stats>, ApiError> {
    let (submissions, cache_hits) = state.db.submission_counts().await?;
    let mut analyses = StatusCounts::default();
    let mut totals = vec![];
    let mut stages = StageName::ALL.map(|name| {
        let tally = StageStats {
            name,
            done: 0,
            failed: 0,
            skipped: 0,
            duration_ms: None,
        };
        (tally, vec![])
    });

    for row in state.db.stat_rows().await? {
        match row.status.as_str() {
            "queued" => analyses.queued += 1,
            "running" => analyses.running += 1,
            "failed" => analyses.failed += 1,
            "done" => {
                analyses.done += 1;
                totals.extend(elapsed_ms(&row.created_at, &row.updated_at));
            }
            _ => {}
        }
        for step in row.steps {
            let Some((tally, durations)) = stages.iter_mut().find(|(t, _)| t.name == step.name)
            else {
                continue;
            };
            match step.state {
                StepState::Done => {
                    tally.done += 1;
                    durations.extend(step.duration_ms);
                }
                StepState::Failed => tally.failed += 1,
                StepState::Skipped => tally.skipped += 1,
                StepState::Pending | StepState::Running => {}
            }
        }
    }

    Ok(Json(Stats {
        analyses,
        submissions,
        cache_hits,
        analysis_ms: percentiles(totals),
        stages: stages
            .into_iter()
            .map(|(tally, durations)| StageStats {
                duration_ms: percentiles(durations),
                ..tally
            })
            .collect(),
    }))
}

/// Milliseconds between two RFC 3339 timestamps.
fn elapsed_ms(from: &str, to: &str) -> Option<u64> {
    let from = DateTime::parse_from_rfc3339(from).ok()?;
    let to = DateTime::parse_from_rfc3339(to).ok()?;
    u64::try_from((to - from).num_milliseconds()).ok()
}

/// Nearest-rank p50 and p95; `None` without values.
fn percentiles(mut values: Vec<u64>) -> Option<Percentiles> {
    if values.is_empty() {
        return None;
    }
    values.sort_unstable();
    let rank = |percent: usize| values[(values.len() * percent).div_ceil(100) - 1];
    Some(Percentiles {
        p50: rank(50),
        p95: rank(95),
    })
}
