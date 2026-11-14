//! Endpoint tests for health, metrics, docs and the committed OpenAPI contract.

mod common;

use common::*;
use junction_contracts::{Health, StageAvailability, StageName, WorkerHealth};
use serde_json::json;
use wiremock::{
    Mock, ResponseTemplate,
    matchers::{method, path},
};

#[tokio::test]
async fn health_reports_worker_stages() {
    let app = TestApp::spawn().await;
    let worker = WorkerHealth {
        stages: vec![StageAvailability {
            name: StageName::Extract,
            implemented: true,
            error: None,
        }],
    };
    Mock::given(method("GET"))
        .and(path("/health"))
        .respond_with(ResponseTemplate::new(200).set_body_json(&worker))
        .mount(&app.worker)
        .await;

    let response = app.http.get(app.url("/api/health")).send().await.unwrap();
    assert_eq!(response.status(), 200);
    let health: Health = response.json().await.unwrap();
    assert_eq!(health.status, "ok");
    assert_eq!(health.pipeline_version, "test");
    assert_eq!(health.worker, Some(worker));
}

#[tokio::test]
async fn health_stays_up_when_the_worker_is_down() {
    let app = TestApp::spawn_with(|c| c.worker_url = "http://127.0.0.1:9".parse().unwrap()).await;
    let response = app.http.get(app.url("/api/health")).send().await.unwrap();
    assert_eq!(response.status(), 200);
    assert_eq!(response.json::<Health>().await.unwrap().worker, None);
}

#[tokio::test]
async fn metrics_serves_the_eval_harness_output() {
    let app = TestApp::spawn().await;
    let missing = app.http.get(app.url("/api/metrics")).send().await.unwrap();
    assert_eq!(missing.status(), 404);

    let metrics = json!({ "single": { "precision": 0.8, "fpr": { "satire": 0.05 } } });
    std::fs::write(&app.state.config.metrics_path, metrics.to_string()).unwrap();
    let response = app.http.get(app.url("/api/metrics")).send().await.unwrap();
    assert_eq!(response.status(), 200);
    assert_eq!(response.json::<serde_json::Value>().await.unwrap(), metrics);
}

#[tokio::test]
async fn graph_serves_the_offline_build() {
    let app = TestApp::spawn().await;
    let missing = app.http.get(app.url("/api/graph")).send().await.unwrap();
    assert_eq!(missing.status(), 404);

    let graph =
        json!({ "counts": { "outlets": 2 }, "edges": [{ "a": "a.example", "b": "b.example" }] });
    std::fs::write(&app.state.config.graph_path, graph.to_string()).unwrap();
    let response = app.http.get(app.url("/api/graph")).send().await.unwrap();
    assert_eq!(response.status(), 200);
    assert_eq!(response.json::<serde_json::Value>().await.unwrap(), graph);
}

#[tokio::test]
async fn docs_and_spec_are_served() {
    let app = TestApp::spawn().await;
    let docs = app.http.get(app.url("/api/docs")).send().await.unwrap();
    assert_eq!(docs.status(), 200);
    assert!(
        docs.headers()["content-type"]
            .to_str()
            .unwrap()
            .starts_with("text/html")
    );

    let spec: serde_json::Value = app
        .http
        .get(app.url("/api/openapi.json"))
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap();
    assert!(spec["paths"]["/api/analyses"]["post"].is_object());
}

#[tokio::test]
async fn responses_carry_a_request_id() {
    let app = TestApp::spawn().await;
    let response = app.http.get(app.url("/api/health")).send().await.unwrap();
    assert!(response.headers().contains_key("x-request-id"));
}

/// `contracts/openapi.json` is what the Python and TypeScript types are generated from;
/// it must match the Rust types. Fix with `mise run contracts`.
#[test]
fn committed_openapi_matches_the_rust_types() {
    let generated = junction_api::routes::openapi().to_pretty_json().unwrap();
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../contracts/openapi.json");
    let committed = std::fs::read_to_string(path).unwrap_or_default();
    assert!(
        committed.trim_end() == generated.trim_end(),
        "contracts/openapi.json is stale: run `mise run contracts` and commit the result"
    );
}
