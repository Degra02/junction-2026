//! Live SQLite source-graph ingestion tests (`D2`):
//! - new analyses add outlets, articles, tracking IDs and ties to `GET /api/graph` and
//!   `GET /api/graph/outlets/{domain}`;
//! - re-running the same input (`?force=true`) updates rows in place without inflating counts;
//! - a failed `graph` step does not block `Db::find_reusable` from serving a cached result.

mod common;

use common::*;
use junction_contracts::{
    AnalysisEvent, AnalysisStatus, Created, GraphObservation, GraphPatch, GraphPatchArticle,
    GraphPatchOutlet, Input, InputKind, StageName, StepState,
};
use serde_json::{Value, json};
use wiremock::ResponseTemplate;

fn sample_graph_patch() -> GraphPatch {
    GraphPatch {
        outlets: vec![
            GraphPatchOutlet {
                domain: "alpha.example".into(),
                operator: "alpha.example".into(),
                outlet_type: None,
                country: Some("IT".into()),
                known_network: None,
            },
            GraphPatchOutlet {
                domain: "news.example".into(),
                operator: "news.example".into(),
                outlet_type: None,
                country: Some("GB".into()),
                known_network: None,
            },
        ],
        articles: vec![
            GraphPatchArticle {
                url: "https://alpha.example/post-1".into(),
                outlet: "alpha.example".into(),
                title: Some("Alpha report".into()),
                published_at: None,
                language: Some("en".into()),
                analysed: true,
                fact_check: false,
                tracking_ids: vec!["G-SHARED111".into(), "GTM-SHARED222".into()],
                outbound_domains: vec!["news.example".into()],
                embedding: vec![],
            },
            GraphPatchArticle {
                url: "https://news.example/budget".into(),
                outlet: "news.example".into(),
                title: Some("Budget report".into()),
                published_at: None,
                language: Some("en".into()),
                analysed: false,
                fact_check: false,
                tracking_ids: vec!["G-SHARED111".into(), "GTM-SHARED222".into()],
                outbound_domains: vec![],
                embedding: vec![],
            },
        ],
        ties: vec![GraphObservation {
            a: "alpha.example".into(),
            b: "news.example".into(),
            kind: "copy".into(),
            keys_a: vec!["https://alpha.example/post-1".into()],
            keys_b: vec!["https://news.example/budget".into()],
            evidence: vec![json!({
                "a": "https://alpha.example/post-1",
                "b": "https://news.example/budget",
                "share": 0.85
            })],
        }],
    }
}

#[tokio::test]
async fn live_analyses_populate_graph_and_reruns_are_idempotent() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[StageName::Graph]).await;
    mount(
        &app.worker,
        StageName::Graph,
        ResponseTemplate::new(200).set_body_json(sample_graph_patch()),
    )
    .await;

    let input = Input {
        kind: InputKind::Url,
        value: "https://alpha.example/post-1".into(),
        context_url: None,
        explanation_language: None,
    };
    let created: Created = app
        .http
        .post(app.url("/api/analyses"))
        .json(&input)
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    let finished = app.wait_finished(created.id).await;
    assert_eq!(finished.status, AnalysisStatus::Done);
    assert_eq!(finished.step(StageName::Graph).state, StepState::Done);

    let g1: Value = app
        .http
        .get(app.url("/api/graph"))
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    assert_eq!(g1["counts"]["analyses"], 1);
    assert_eq!(g1["counts"]["outlets"], 2);
    assert_eq!(g1["counts"]["articles"], 2);
    assert_eq!(g1["counts"]["clusters"], 1);

    let detail: Value = app
        .http
        .get(app.url("/api/graph/outlets/www.alpha.example"))
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    assert_eq!(detail["outlet"]["domain"], "alpha.example");
    assert_eq!(detail["outlet"]["analysed"], 1);
    assert_eq!(detail["cluster"]["id"], 1);
    assert_eq!(detail["ties"].as_array().unwrap().len(), 1);

    let missing = app
        .http
        .get(app.url("/api/graph/outlets/unknown.example"))
        .send()
        .await
        .unwrap();
    assert_eq!(missing.status(), 404);

    let forced: Created = app
        .http
        .post(app.url("/api/analyses?force=true"))
        .json(&input)
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    assert!(!forced.cached);
    app.wait_finished(forced.id).await;

    let g2: Value = app
        .http
        .get(app.url("/api/graph"))
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    assert_eq!(g2["counts"], g1["counts"]);
}

#[tokio::test]
async fn failed_graph_step_still_allows_cache_reuse() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[StageName::Graph]).await;
    mount(
        &app.worker,
        StageName::Graph,
        ResponseTemplate::new(500).set_body_string("graph worker error"),
    )
    .await;

    let first_id = app.submit(PARAGRAPH).await;
    let finished = app.wait_finished(first_id).await;
    assert_eq!(finished.status, AnalysisStatus::Done);
    assert_eq!(finished.step(StageName::Graph).state, StepState::Failed);

    let second: Created = app
        .http
        .post(app.url("/api/analyses"))
        .json(&json!({ "kind": "text", "value": PARAGRAPH }))
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    assert!(second.cached);
    assert_eq!(second.id, first_id);
}

#[tokio::test]
async fn legacy_analyses_without_graph_step_replay_and_rerun_cleanly() {
    let app = TestApp::spawn().await;
    mount_pipeline(&app.worker, &[]).await;

    let id = app.submit(PARAGRAPH).await;
    let mut legacy = app.wait_finished(id).await;
    legacy.steps.retain(|s| s.name != StageName::Graph);
    assert_eq!(legacy.steps.len(), 8);
    app.state.db.save(&legacy).await.unwrap();

    let events = app
        .read_event_stream(&format!("/api/analyses/{id}/events?replay=true"))
        .await;
    let Some(AnalysisEvent::Snapshot { analysis: first }) = events.first() else {
        panic!("expected snapshot first: {events:?}");
    };
    assert_eq!(first.steps.len(), 8);
    assert!(matches!(events.last(), Some(AnalysisEvent::Done { .. })));

    let rerun: Created = app
        .http
        .post(app.url(&format!("/api/analyses/{id}/rerun?from=signals_single")))
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    let after = app.wait_finished(rerun.id).await;
    assert_eq!(after.status, AnalysisStatus::Done);
    assert_eq!(after.step(StageName::Graph).state, StepState::Done);
}
