//! Endpoint tests for what keeps the demo honest and alive: cache rules, worker errors and
//! restarts, re-runs, replays, the queue, live progress, kill switches, the time budget, usage
//! stats and database backups.

mod common;

use std::time::Duration;

use common::*;
use junction_api::db::Db;
use junction_contracts::*;
use serde_json::json;
use uuid::Uuid;
use wiremock::{
    Mock, MockServer, ResponseTemplate,
    matchers::{method, path, path_regex},
};

fn step(a: &Analysis, stage: StageName) -> &Step {
    a.steps.iter().find(|s| s.name == stage).expect("step")
}

/// Mounts a response for `stage` that is used once, before the mocks mounted after it.
async fn mount_once(worker: &MockServer, stage: StageName, response: ResponseTemplate) {
    Mock::given(method("POST"))
        .and(path(format!("/stages/{stage}")))
        .respond_with(response)
        .up_to_n_times(1)
        .mount(worker)
        .await;
}

async fn post(app: &TestApp, path: &str, body: Option<serde_json::Value>) -> reqwest::Response {
    let request = app.http.post(app.url(path));
    let request = match body {
        Some(body) => request.json(&body),
        None => request,
    };
    request.send().await.expect("request")
}

#[tokio::test]
async fn a_result_with_a_failed_step_is_not_reused() {
    let app = TestApp::spawn().await;
    mount_once(&app.worker, StageName::Retrieve, ResponseTemplate::new(500)).await;
    mount_pipeline(&app.worker, &[]).await;

    let degraded = app.submit(PARAGRAPH).await;
    let a = app.wait_finished(degraded).await;
    assert_eq!(a.status, AnalysisStatus::Done);
    assert_eq!(step(&a, StageName::Retrieve).state, StepState::Failed);

    let clean = app.submit(PARAGRAPH).await;
    assert_ne!(clean, degraded, "the degraded result is not served again");
    let a = app.wait_finished(clean).await;
    assert!(a.steps.iter().all(|s| s.state == StepState::Done));

    let again: Created = app.post_text(PARAGRAPH).await.json().await.unwrap();
    assert_eq!(
        again,
        Created {
            id: clean,
            cached: true
        }
    );
}

#[tokio::test]
async fn force_runs_again_despite_a_reusable_result() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[]).await;
    let first = app.submit(PARAGRAPH).await;
    app.wait_finished(first).await;

    let body = json!({ "kind": "text", "value": PARAGRAPH });
    let forced = post(&app, "/api/analyses?force=true", Some(body)).await;
    assert_eq!(forced.status(), 202);
    let forced: Created = forced.json().await.unwrap();
    assert!(!forced.cached);
    assert_ne!(forced.id, first);
    app.wait_finished(forced.id).await;
    assert_eq!(app.stage_requests(StageName::Extract).await.len(), 2);
}

#[tokio::test]
async fn only_the_worker_s_own_error_message_reaches_the_record() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[StageName::Retrieve, StageName::Explain]).await;
    let worded = json!({ "error": "stage_failed", "message": "no source answered in time" });
    mount(
        &app.worker,
        StageName::Retrieve,
        ResponseTemplate::new(500).set_body_json(worded),
    )
    .await;
    // Not the worker's error format: e.g. a traceback page with a key in a URL.
    mount(
        &app.worker,
        StageName::Explain,
        ResponseTemplate::new(502).set_body_string("GET https://api.example/?key=SECRET failed"),
    )
    .await;

    let a = app.wait_finished(app.submit(PARAGRAPH).await).await;
    assert_eq!(
        step(&a, StageName::Retrieve).error.as_deref(),
        Some("no source answered in time")
    );
    assert_eq!(
        step(&a, StageName::Explain).error.as_deref(),
        Some("worker returned 502 Bad Gateway")
    );
}

#[tokio::test]
async fn stage_calls_wait_for_a_restarting_worker() {
    // Reserve a port, then start the worker on it only after the analysis was submitted.
    let reserved = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let addr = reserved.local_addr().unwrap();
    drop(reserved);
    let app = TestApp::spawn_with(|c| {
        c.worker_url = format!("http://{addr}").parse().unwrap();
        c.worker_connect_wait = Duration::from_secs(8);
    })
    .await;
    let id = app.submit(PARAGRAPH).await;

    tokio::time::sleep(Duration::from_millis(200)).await;
    let listener = std::net::TcpListener::bind(addr).unwrap();
    let worker = MockServer::builder().listener(listener).start().await;
    mount_pipeline(&worker, &[]).await;

    let a = app.wait_finished(id).await;
    assert_eq!(a.status, AnalysisStatus::Done, "{:?}", a.steps);
}

#[tokio::test]
async fn rerun_keeps_the_earlier_stages_and_runs_the_rest_again() {
    let app = TestApp::spawn().await;
    mount_once(&app.worker, StageName::Retrieve, ResponseTemplate::new(500)).await;
    mount_pipeline(&app.worker, &[]).await;
    let source = app.submit(PARAGRAPH).await;
    let before = app.wait_finished(source).await;
    assert_eq!(before.context, []);

    let response = post(
        &app,
        &format!("/api/analyses/{source}/rerun?from=retrieve"),
        None,
    )
    .await;
    assert_eq!(response.status(), 202);
    let rerun: Created = response.json().await.unwrap();
    assert_ne!(rerun.id, source);
    let after = app.wait_finished(rerun.id).await;

    assert_eq!(after.status, AnalysisStatus::Done);
    assert!(after.steps.iter().all(|s| s.state == StepState::Done));
    assert_eq!(after.claims, before.claims, "understand output was kept");
    assert_eq!(after.context.len(), 1);
    let ids: Vec<_> = after.evidence.iter().map(|e| e.id.as_str()).collect();
    assert_eq!(ids, ["s1", "c1"], "old evidence was replaced, not appended");
    for (stage, calls) in [
        (StageName::Extract, 1),
        (StageName::Understand, 1),
        (StageName::Retrieve, 2),
        (StageName::Score, 2),
    ] {
        assert_eq!(app.stage_requests(stage).await.len(), calls, "{stage}");
    }
    assert_eq!(app.get(source).await, before, "the source is untouched");

    let cached: Created = app.post_text(PARAGRAPH).await.json().await.unwrap();
    assert_eq!(cached.id, rerun.id, "the re-run is now the cached result");
}

#[tokio::test]
async fn rerun_rejects_running_analyses_and_unknown_stages() {
    let app = TestApp::spawn().await;
    mount(
        &app.worker,
        StageName::Extract,
        ResponseTemplate::new(200)
            .set_body_json(valid_patch(StageName::Extract))
            .set_delay(Duration::from_millis(500)),
    )
    .await;
    let id = app.submit(PARAGRAPH).await;

    let running = post(&app, &format!("/api/analyses/{id}/rerun?from=score"), None).await;
    assert_eq!(running.status(), 409);
    assert_eq!(running.json::<ErrorBody>().await.unwrap().error, "conflict");
    let unknown = post(&app, &format!("/api/analyses/{id}/rerun?from=nope"), None).await;
    assert_eq!(unknown.status(), 422);
    let missing = Uuid::now_v7();
    let missing = post(
        &app,
        &format!("/api/analyses/{missing}/rerun?from=score"),
        None,
    )
    .await;
    assert_eq!(missing.status(), 404);
}

#[tokio::test]
async fn replay_plays_a_finished_analysis_back_from_an_empty_snapshot() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[StageName::Explain]).await;
    mount(&app.worker, StageName::Explain, ResponseTemplate::new(501)).await;
    let id = app.submit(PARAGRAPH).await;
    let finished = app.wait_finished(id).await;

    let events = app
        .read_event_stream(&format!("/api/analyses/{id}/events?replay=true"))
        .await;
    let Some(AnalysisEvent::Snapshot { analysis: first }) = events.first() else {
        panic!("first event is a snapshot: {events:?}");
    };
    assert_eq!(first.status, AnalysisStatus::Running);
    assert!(first.document.is_none() && first.scores.is_none() && first.evidence.is_empty());
    assert!(first.steps.iter().all(|s| s.state == StepState::Pending));

    let states: Vec<(StageName, StepState)> = events
        .iter()
        .filter_map(|e| match e {
            AnalysisEvent::Step { step } => Some((step.name, step.state)),
            _ => None,
        })
        .collect();
    let mut expected = vec![];
    for stage in &StageName::ALL[..7] {
        expected.push((*stage, StepState::Running));
        expected.push((*stage, StepState::Done));
    }
    expected.push((StageName::Explain, StepState::Skipped));
    expected.push((StageName::Graph, StepState::Running));
    expected.push((StageName::Graph, StepState::Done));
    assert_eq!(states, expected);
    assert_eq!(
        events.last(),
        Some(&AnalysisEvent::Done {
            analysis: Box::new(finished)
        })
    );
    assert_eq!(
        app.stage_requests(StageName::Extract).await.len(),
        1,
        "a replay calls no stage"
    );
}

#[tokio::test]
async fn queued_analyses_know_their_place() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[StageName::Extract]).await;
    mount(
        &app.worker,
        StageName::Extract,
        ResponseTemplate::new(200)
            .set_body_json(valid_patch(StageName::Extract))
            .set_delay(Duration::from_millis(300)),
    )
    .await;
    let first = app.submit("first text").await;
    let second = app.submit("second text").await;
    let third = app.submit("third text").await;

    let waiting = app.get(third).await;
    assert_eq!(waiting.status, AnalysisStatus::Queued);
    assert_eq!(waiting.queue_position, Some(2));
    assert_eq!(app.get(second).await.queue_position, Some(1));

    let events = app.read_events(third).await;
    assert!(
        events.contains(&AnalysisEvent::Queue { position: 1 }),
        "moved up when the first one started the second: {events:?}"
    );
    let done = app.wait_finished(third).await;
    assert_eq!(done.queue_position, None);
    assert_eq!(app.get(first).await.status, AnalysisStatus::Done);
}

#[tokio::test]
async fn progress_notes_of_a_running_stage_are_streamed() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[StageName::Retrieve]).await;
    mount(
        &app.worker,
        StageName::Retrieve,
        ResponseTemplate::new(200)
            .set_body_json(valid_patch(StageName::Retrieve))
            .set_delay(Duration::from_millis(1500)),
    )
    .await;
    Mock::given(method("GET"))
        .and(path_regex("^/progress/[0-9a-f-]{36}$"))
        .respond_with(
            ResponseTemplate::new(200).set_body_json(json!({ "retrieve": "9 sources so far" })),
        )
        .mount(&app.worker)
        .await;
    let id = app.submit(PARAGRAPH).await;

    let events = app.read_events(id).await;
    let notes: Vec<&Step> = events
        .iter()
        .filter_map(|e| match e {
            AnalysisEvent::Step { step } if step.detail.as_deref() == Some("9 sources so far") => {
                Some(step)
            }
            _ => None,
        })
        .collect();
    assert_eq!(notes.len(), 1, "an unchanged note is sent once: {events:?}");
    assert_eq!(notes[0].name, StageName::Retrieve);
    assert_eq!(notes[0].state, StepState::Running);
    let done = app.get(id).await;
    assert_eq!(
        step(&done, StageName::Retrieve).detail.as_deref(),
        Some("1 source"),
        "the stored detail comes from the patch"
    );
}

#[tokio::test]
async fn disabled_stages_are_skipped_without_calling_the_worker() {
    let app = TestApp::spawn_with(|c| c.stages_disabled = vec![StageName::Explain]).await;
    mount_pipeline(&app.worker, &[]).await;

    let a = app.wait_finished(app.submit(PARAGRAPH).await).await;
    assert_eq!(a.status, AnalysisStatus::Done);
    let explain = step(&a, StageName::Explain);
    assert_eq!(explain.state, StepState::Skipped);
    assert_eq!(
        explain.error.as_deref(),
        Some("switched off by the operator")
    );
    assert_eq!(app.stage_requests(StageName::Explain).await, []);
}

#[tokio::test]
async fn stages_past_the_time_budget_are_skipped() {
    let app = TestApp::spawn_with(|c| c.analysis_timeout = Duration::from_millis(400)).await;
    mount_pipeline(&app.worker, &[StageName::Understand]).await;
    mount(
        &app.worker,
        StageName::Understand,
        ResponseTemplate::new(200)
            .set_body_json(valid_patch(StageName::Understand))
            .set_delay(Duration::from_secs(5)),
    )
    .await;

    let a = app.wait_finished(app.submit(PARAGRAPH).await).await;
    let understand = step(&a, StageName::Understand);
    assert_eq!(understand.state, StepState::Failed);
    assert!(
        understand.duration_ms.unwrap() < 1_000,
        "cut at the budget, not at the 2 s stage timeout: {understand:?}"
    );
    for later in &a.steps[2..] {
        assert_eq!(later.state, StepState::Skipped, "{later:?}");
        assert_eq!(later.error.as_deref(), Some("the analysis ran out of time"));
    }
    assert_eq!(a.status, AnalysisStatus::Failed);
}

#[tokio::test]
async fn stats_count_submissions_cache_hits_and_stage_runs() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[StageName::Explain]).await;
    mount(&app.worker, StageName::Explain, ResponseTemplate::new(501)).await;
    let id = app.submit(PARAGRAPH).await;
    app.wait_finished(id).await;
    let again: Created = app.post_text(PARAGRAPH).await.json().await.unwrap();
    assert!(again.cached);
    let other = app.submit("another text").await;
    app.wait_finished(other).await;

    let response = app.http.get(app.url("/api/stats")).send().await.unwrap();
    assert_eq!(response.status(), 200);
    let stats: Stats = response.json().await.unwrap();
    assert_eq!(stats.submissions, 3);
    assert_eq!(stats.cache_hits, 1);
    assert_eq!(
        stats.analyses,
        StatusCounts {
            done: 2,
            ..StatusCounts::default()
        }
    );
    assert!(stats.analysis_ms.is_some());
    let names: Vec<StageName> = stats.stages.iter().map(|s| s.name).collect();
    assert_eq!(names, StageName::ALL);
    let extract = &stats.stages[0];
    assert_eq!((extract.done, extract.failed, extract.skipped), (2, 0, 0));
    assert!(extract.duration_ms.is_some());
    let explain = &stats.stages[7];
    assert_eq!((explain.done, explain.skipped), (0, 2));
    assert_eq!(explain.duration_ms, None);
}

#[tokio::test]
async fn backups_are_consistent_copies_and_old_ones_are_pruned() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[]).await;
    let id = app.submit(PARAGRAPH).await;
    let stored = app.wait_finished(id).await;

    let dir = app.state.backup_dir();
    let mut newest = None;
    for _ in 0..3 {
        newest = Some(app.state.db.backup(&dir, 2).await.unwrap());
        tokio::time::sleep(Duration::from_millis(5)).await;
    }
    let copies = std::fs::read_dir(&dir).unwrap().count();
    assert_eq!(copies, 2, "only the newest two are kept");

    let copy = Db::open(&newest.unwrap()).await.unwrap();
    assert_eq!(copy.get(id).await.unwrap(), Some(stored));
}
