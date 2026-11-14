//! Endpoint tests for `/api/analyses`: lifecycle, stage failures, contract enforcement,
//! caching, validation, rate limiting, SSE, restart recovery and shutdown.

mod common;

use std::time::Duration;

use common::*;
use junction_api::{AppState, db::Db};
use junction_contracts::*;
use serde_json::json;
use uuid::Uuid;
use wiremock::ResponseTemplate;

fn step(a: &Analysis, stage: StageName) -> &Step {
    a.steps.iter().find(|s| s.name == stage).expect("step")
}

#[tokio::test]
async fn full_pipeline_produces_a_scored_record() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[]).await;

    let response = app.post_text(PARAGRAPH).await;
    assert_eq!(response.status(), 202);
    let created: Created = response.json().await.unwrap();
    assert!(!created.cached);

    let a = app.wait_finished(created.id).await;
    assert_eq!(a.status, AnalysisStatus::Done, "{:?}", a.error);
    assert!(
        a.steps.iter().all(|s| s.state == StepState::Done),
        "{:?}",
        a.steps
    );
    assert!(a.steps.iter().all(|s| s.duration_ms.is_some()));
    assert_eq!(a.claims.len(), 1);
    assert_eq!(a.context[0].in_story, Some(true));
    let ids: Vec<_> = a.evidence.iter().map(|e| e.id.as_str()).collect();
    assert_eq!(
        ids,
        ["s1", "c1"],
        "parallel signal stages merged in schedule order"
    );
    assert_eq!(a.scores.as_ref().unwrap().single.confidence, Some(0.71));
    assert_eq!(a.explanation.as_ref().unwrap().reasons.len(), 1);
    assert_eq!(
        step(&a, StageName::Retrieve).detail.as_deref(),
        Some("1 source")
    );
    assert_eq!(
        step(&a, StageName::Story).detail.as_deref(),
        Some("1 of 1 items in the story")
    );
}

#[tokio::test]
async fn each_stage_receives_the_merged_record_of_the_earlier_stages() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[]).await;
    let id = app.submit(PARAGRAPH).await;
    app.wait_finished(id).await;

    let extract = app.stage_requests(StageName::Extract).await;
    assert_eq!(extract.len(), 1);
    assert_eq!(extract[0].input.value, PARAGRAPH);
    assert!(extract[0].document.is_none());

    let score = app.stage_requests(StageName::Score).await;
    assert_eq!(score[0].evidence.len(), 2, "score sees both signal stages");
    assert_eq!(score[0].claims.len(), 1);

    let single = app.stage_requests(StageName::SignalsSingle).await;
    let coordinated = app.stage_requests(StageName::SignalsCoordinated).await;
    assert!(single[0].evidence.is_empty() && coordinated[0].evidence.is_empty());
}

#[tokio::test]
async fn unimplemented_stages_are_skipped_and_the_rest_still_runs() {
    let app = TestApp::spawn().await;
    let missing = [
        StageName::Understand,
        StageName::Retrieve,
        StageName::Story,
        StageName::Explain,
    ];
    mount_pipeline(&app.worker, &missing).await;
    for stage in missing {
        mount(&app.worker, stage, ResponseTemplate::new(501)).await;
    }

    let a = app.wait_finished(app.submit(PARAGRAPH).await).await;
    assert_eq!(a.status, AnalysisStatus::Done);
    for stage in missing {
        let s = step(&a, stage);
        assert_eq!(s.state, StepState::Skipped, "{stage}");
        assert_eq!(s.error.as_deref(), Some("not implemented yet"));
    }
    // c1 cites ctx1, which retrieve never produced: dropped, not trusted.
    assert_eq!(
        a.evidence.iter().map(|e| e.id.as_str()).collect::<Vec<_>>(),
        ["s1"]
    );
    let detail = step(&a, StageName::SignalsCoordinated)
        .detail
        .clone()
        .unwrap();
    assert!(detail.contains("unknown context `ctx1`"), "{detail}");
}

#[tokio::test]
async fn extract_failure_fails_the_analysis_and_skips_everything_else() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[StageName::Extract]).await;
    mount(
        &app.worker,
        StageName::Extract,
        ResponseTemplate::new(500).set_body_string("boom"),
    )
    .await;

    let a = app.wait_finished(app.submit(PARAGRAPH).await).await;
    assert_eq!(a.status, AnalysisStatus::Failed);
    let error = a.error.unwrap();
    assert!(
        error.starts_with("could not read the input: extract worker returned 500"),
        "{error}"
    );
    assert!(a.steps[1..].iter().all(|s| s.state == StepState::Skipped));
    let requests = app.worker.received_requests().await.unwrap();
    assert_eq!(requests.len(), 1, "no stage after extract was called");
}

#[tokio::test]
async fn missing_score_fails_the_analysis_and_skips_explain() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[StageName::Score]).await;
    mount(&app.worker, StageName::Score, ResponseTemplate::new(501)).await;

    let a = app.wait_finished(app.submit(PARAGRAPH).await).await;
    assert_eq!(a.status, AnalysisStatus::Failed);
    assert_eq!(
        a.error.as_deref(),
        Some("no score was produced: score not implemented yet")
    );
    assert_eq!(
        step(&a, StageName::Explain).error.as_deref(),
        Some("needs the scores")
    );
}

#[tokio::test]
async fn contract_violations_fail_only_their_step() {
    let app = TestApp::spawn().await;
    let broken = [StageName::Retrieve, StageName::SignalsSingle];
    mount_pipeline(&app.worker, &broken).await;
    // Unknown field: patches deny unknown fields so typos surface.
    mount(
        &app.worker,
        StageName::Retrieve,
        ResponseTemplate::new(200)
            .set_body_json(json!({ "context": [], "detail": null, "extra": 1 })),
    )
    .await;
    // A coordinated family from the single-actor stage.
    let mut wrong = valid_patch(StageName::SignalsCoordinated);
    wrong["evidence"][0]["id"] = json!("s9");
    mount(
        &app.worker,
        StageName::SignalsSingle,
        ResponseTemplate::new(200).set_body_json(wrong),
    )
    .await;
    // Score cites s1, which no longer exists, so score fails too: assert per step instead.

    let a = app.wait_finished(app.submit(PARAGRAPH).await).await;
    let retrieve = step(&a, StageName::Retrieve);
    assert_eq!(retrieve.state, StepState::Failed);
    assert!(
        retrieve
            .error
            .as_ref()
            .unwrap()
            .contains("does not match the contract")
    );
    let single = step(&a, StageName::SignalsSingle);
    assert_eq!(single.state, StepState::Failed);
    assert!(
        single
            .error
            .as_ref()
            .unwrap()
            .contains("rejected by the contract")
    );
    assert_eq!(
        step(&a, StageName::SignalsCoordinated).state,
        StepState::Done
    );
    assert!(a.evidence.iter().all(|e| e.id != "s9"));
}

#[tokio::test]
async fn slow_stage_times_out() {
    let app = TestApp::spawn_with(|c| c.stage_timeout = Duration::from_millis(200)).await;
    mount_pipeline(&app.worker, &[StageName::Retrieve]).await;
    mount(
        &app.worker,
        StageName::Retrieve,
        ResponseTemplate::new(200)
            .set_body_json(valid_patch(StageName::Retrieve))
            .set_delay(Duration::from_secs(2)),
    )
    .await;

    let a = app.wait_finished(app.submit(PARAGRAPH).await).await;
    let retrieve = step(&a, StageName::Retrieve);
    assert_eq!(retrieve.state, StepState::Failed);
    assert_eq!(retrieve.error.as_deref(), Some("timed out after 200ms"));
    assert_eq!(a.status, AnalysisStatus::Done, "later stages still ran");
}

#[tokio::test]
async fn resubmitting_the_same_input_reuses_the_analysis() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[]).await;
    let first = app.submit(PARAGRAPH).await;
    app.wait_finished(first).await;

    let again = app
        .post_text(&format!("  {}\n", PARAGRAPH.replace(' ', "  ")))
        .await;
    let created: Created = again.json().await.unwrap();
    assert_eq!(
        created,
        Created {
            id: first,
            cached: true
        }
    );
    assert_eq!(
        app.stage_requests(StageName::Extract).await.len(),
        1,
        "pipeline ran once"
    );
}

#[tokio::test]
async fn failed_analyses_are_not_reused() {
    let app = TestApp::spawn().await;
    mount(&app.worker, StageName::Extract, ResponseTemplate::new(500)).await;
    let first = app.submit(PARAGRAPH).await;
    app.wait_finished(first).await;

    let second = app.submit(PARAGRAPH).await;
    assert_ne!(first, second);
}

#[tokio::test]
async fn invalid_input_is_rejected_with_a_json_error() {
    let app = TestApp::spawn_with(|c| c.max_input_chars = 20).await;
    let cases = [
        json!({ "kind": "text", "value": "   " }),
        json!({ "kind": "text", "value": "x".repeat(21) }),
        json!({ "kind": "url", "value": "ftp://example.com/a" }),
        json!({ "kind": "url", "value": "not a url" }),
        json!({ "kind": "image", "value": "x" }),
        json!({ "value": "missing kind" }),
    ];
    for body in cases {
        let response = app
            .http
            .post(app.url("/api/analyses"))
            .json(&body)
            .send()
            .await
            .unwrap();
        assert_eq!(response.status(), 422, "{body}");
        let error: ErrorBody = response.json().await.unwrap();
        assert_eq!(error.error, "invalid_input", "{body}");
    }
    assert!(app.worker.received_requests().await.unwrap().is_empty());
}

#[tokio::test]
async fn url_input_is_accepted_and_passed_to_extract() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[]).await;
    let response = app
        .http
        .post(app.url("/api/analyses"))
        .json(&json!({ "kind": "url", "value": " https://news.example/a?b=1 " }))
        .send()
        .await
        .unwrap();
    let id = response.json::<Created>().await.unwrap().id;
    app.wait_finished(id).await;
    let sent = &app.stage_requests(StageName::Extract).await[0].input;
    assert_eq!(
        sent,
        &Input {
            kind: InputKind::Url,
            value: "https://news.example/a?b=1".into()
        }
    );
}

#[tokio::test]
async fn unknown_or_malformed_ids_return_404_json() {
    let app = TestApp::spawn().await;
    for path in [
        format!("/api/analyses/{}", Uuid::now_v7()),
        "/api/analyses/not-a-uuid".to_owned(),
        format!("/api/analyses/{}/events", Uuid::now_v7()),
        "/api/nope".to_owned(),
    ] {
        let response = app.http.get(app.url(&path)).send().await.unwrap();
        assert_eq!(response.status(), 404, "{path}");
        let error: ErrorBody = response.json().await.unwrap();
        assert_eq!(error.error, "not_found", "{path}");
    }
}

#[tokio::test]
async fn new_analyses_are_rate_limited_per_client_ip() {
    let app = TestApp::spawn_with(|c| {
        c.rate_limit_per_minute = 2;
        c.trust_proxy = true;
    })
    .await;
    mount_pipeline(&app.worker, &[]).await;
    let post = |ip: &'static str, n: usize| {
        app.http
            .post(app.url("/api/analyses"))
            .header("x-forwarded-for", format!("203.0.113.9, {ip}"))
            .json(&json!({ "kind": "text", "value": format!("text {n}") }))
            .send()
    };

    assert_eq!(post("198.51.100.1", 1).await.unwrap().status(), 202);
    assert_eq!(post("198.51.100.1", 2).await.unwrap().status(), 202);
    let limited = post("198.51.100.1", 3).await.unwrap();
    assert_eq!(limited.status(), 429);
    assert_eq!(
        limited.json::<ErrorBody>().await.unwrap().error,
        "rate_limited"
    );
    assert_eq!(
        post("198.51.100.2", 4).await.unwrap().status(),
        202,
        "other client unaffected"
    );

    let health = app.http.get(app.url("/api/health")).send().await.unwrap();
    assert_eq!(health.status(), 200, "reads are not limited");
}

#[tokio::test]
async fn events_stream_snapshot_steps_and_done() {
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
    let id = app.submit(PARAGRAPH).await;

    let events = app.read_events(id).await;
    assert!(matches!(
        events.first(),
        Some(AnalysisEvent::Snapshot { .. })
    ));
    let Some(AnalysisEvent::Done { analysis }) = events.last() else {
        panic!("last event is done: {events:?}");
    };
    assert_eq!(analysis.status, AnalysisStatus::Done);
    let finished: Vec<&Step> = events
        .iter()
        .filter_map(|e| match e {
            AnalysisEvent::Step { step } if step.state == StepState::Done => Some(step),
            _ => None,
        })
        .collect();
    assert_eq!(finished.len(), StageName::ALL.len(), "{finished:?}");
    assert!(
        finished.iter().all(|s| s.duration_ms.is_some()),
        "streamed steps carry their duration: {finished:?}"
    );
}

#[tokio::test]
async fn events_of_a_finished_analysis_are_snapshot_then_done() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[]).await;
    let id = app.submit(PARAGRAPH).await;
    app.wait_finished(id).await;

    let events = app.read_events(id).await;
    assert_eq!(events.len(), 2);
    assert!(matches!(events[0], AnalysisEvent::Snapshot { .. }));
    assert!(matches!(events[1], AnalysisEvent::Done { .. }));
}

#[tokio::test]
async fn shutdown_ends_open_event_streams() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[StageName::Extract]).await;
    mount(
        &app.worker,
        StageName::Extract,
        ResponseTemplate::new(200).set_delay(Duration::from_secs(30)),
    )
    .await;
    let id = app.submit(PARAGRAPH).await;

    let shutdown = app.state.shutdown.clone();
    tokio::spawn(async move {
        tokio::time::sleep(Duration::from_millis(200)).await;
        shutdown.cancel();
    });
    let events = app.read_events(id).await;
    assert!(matches!(
        events.as_slice(),
        [AnalysisEvent::Snapshot { .. }, ..]
    ));
}

#[tokio::test]
async fn analyses_interrupted_by_a_restart_are_marked_failed() {
    let dir = tempfile::tempdir().unwrap();
    let config = test_config(&dir, "http://127.0.0.1:9");
    let db = Db::open(&config.database_path).await.unwrap();
    let mut running = Analysis::new(
        Uuid::now_v7(),
        Input {
            kind: InputKind::Text,
            value: "x".into(),
        },
        "test".into(),
        chrono::Utc::now(),
    );
    running.status = AnalysisStatus::Running;
    running.steps[0].state = StepState::Running;
    db.insert(&running, "hash").await.unwrap();
    drop(db);

    let state = AppState::new(config).await.unwrap();
    let a = state.db.get(running.id).await.unwrap().unwrap();
    assert_eq!(a.status, AnalysisStatus::Failed);
    assert!(a.error.unwrap().contains("interrupted"));
    assert!(a.steps.iter().all(|s| s.state == StepState::Skipped));
    assert_eq!(
        state.db.find_reusable("hash").await.unwrap(),
        None,
        "resubmission runs again"
    );
}
