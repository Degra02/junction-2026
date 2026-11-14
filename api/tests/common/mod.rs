//! Test harness: the real server on 127.0.0.1:0, a temp-file SQLite database and a wiremock
//! worker. Each nextest test runs in its own process, so nothing is shared between tests.
#![allow(dead_code, clippy::missing_const_for_fn)]

use std::{net::SocketAddr, time::Duration};

use chrono::Utc;
use futures_util::StreamExt as _;
use junction_api::{AppState, config::Config};
use junction_contracts::*;
use serde_json::{Value, json};
use tempfile::TempDir;
use tokio::net::TcpListener;
use uuid::Uuid;
use wiremock::{
    Mock, MockServer, ResponseTemplate,
    matchers::{method, path},
};

pub struct TestApp {
    pub base: String,
    pub http: reqwest::Client,
    pub state: AppState,
    pub worker: MockServer,
    _dir: TempDir,
}

impl TestApp {
    pub async fn spawn() -> Self {
        Self::spawn_with(|_| {}).await
    }

    pub async fn spawn_with(tweak: impl FnOnce(&mut Config)) -> Self {
        let worker = MockServer::start().await;
        let dir = tempfile::tempdir().expect("temp dir");
        let mut config = test_config(&dir, &worker.uri());
        tweak(&mut config);
        let state = AppState::new(config).await.expect("app state");
        let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind");
        let addr: SocketAddr = listener.local_addr().expect("addr");
        tokio::spawn(junction_api::serve(listener, state.clone()));
        Self {
            base: format!("http://{addr}"),
            http: reqwest::Client::new(),
            state,
            worker,
            _dir: dir,
        }
    }

    pub fn url(&self, path: &str) -> String {
        format!("{}{path}", self.base)
    }

    pub async fn post_text(&self, text: &str) -> reqwest::Response {
        self.http
            .post(self.url("/api/analyses"))
            .json(&json!({ "kind": "text", "value": text }))
            .send()
            .await
            .expect("request")
    }

    /// Submits `text` and returns the new analysis ID.
    pub async fn submit(&self, text: &str) -> Uuid {
        let response = self.post_text(text).await;
        assert_eq!(response.status(), 202);
        response.json::<Created>().await.expect("created").id
    }

    pub async fn get(&self, id: Uuid) -> Analysis {
        let response = self
            .http
            .get(self.url(&format!("/api/analyses/{id}")))
            .send()
            .await
            .expect("request");
        assert_eq!(response.status(), 200);
        response.json().await.expect("analysis")
    }

    /// Polls until the analysis is done or failed.
    pub async fn wait_finished(&self, id: Uuid) -> Analysis {
        tokio::time::timeout(Duration::from_secs(10), async {
            loop {
                let a = self.get(id).await;
                if matches!(a.status, AnalysisStatus::Done | AnalysisStatus::Failed) {
                    return a;
                }
                tokio::time::sleep(Duration::from_millis(20)).await;
            }
        })
        .await
        .expect("analysis finished within 10 s")
    }

    /// Reads SSE events until the server closes the stream.
    pub async fn read_events(&self, id: Uuid) -> Vec<AnalysisEvent> {
        let response = self
            .http
            .get(self.url(&format!("/api/analyses/{id}/events")))
            .send()
            .await
            .expect("request");
        assert_eq!(response.status(), 200);
        assert_eq!(
            response.headers()["content-type"],
            "text/event-stream",
            "SSE content type"
        );
        let mut body = response.bytes_stream();
        let mut buffer = String::new();
        let mut events = vec![];
        let read = async {
            while let Some(chunk) = body.next().await {
                buffer.push_str(&String::from_utf8_lossy(&chunk.expect("chunk")));
                while let Some(end) = buffer.find("\n\n") {
                    let frame: String = buffer.drain(..end + 2).collect();
                    if let Some(event) = parse_frame(&frame) {
                        events.push(event);
                    }
                }
            }
        };
        tokio::time::timeout(Duration::from_secs(10), read)
            .await
            .expect("stream closed within 10 s");
        events
    }

    /// Requests the worker received for `stage`, parsed as the `Analysis` it was sent.
    pub async fn stage_requests(&self, stage: StageName) -> Vec<Analysis> {
        let suffix = format!("/stages/{stage}");
        self.worker
            .received_requests()
            .await
            .unwrap_or_default()
            .into_iter()
            .filter(|r| r.url.path() == suffix)
            .map(|r| serde_json::from_slice(&r.body).expect("worker got an Analysis"))
            .collect()
    }
}

/// Parses one `event: …\ndata: …` frame; keep-alive comments return `None`.
fn parse_frame(frame: &str) -> Option<AnalysisEvent> {
    let mut name = None;
    let mut data = String::new();
    for line in frame.lines() {
        if let Some(v) = line.strip_prefix("event:") {
            name = Some(v.trim().to_owned());
        } else if let Some(v) = line.strip_prefix("data:") {
            data.push_str(v.trim_start());
        }
    }
    let event: AnalysisEvent = serde_json::from_str(&data).ok()?;
    assert_eq!(
        name.as_deref(),
        Some(event.name()),
        "SSE event name matches payload type"
    );
    Some(event)
}

pub fn test_config(dir: &TempDir, worker_url: &str) -> Config {
    Config {
        addr: "127.0.0.1:0".parse().expect("addr"),
        database_path: dir.path().join("app.db"),
        worker_url: worker_url.parse().expect("worker url"),
        stage_timeout: Duration::from_secs(2),
        max_concurrent_analyses: 1,
        max_input_chars: 1_000,
        rate_limit_per_minute: 0,
        trust_proxy: false,
        metrics_path: dir.path().join("metrics.json"),
        pipeline_version: "test".into(),
    }
}

pub const PARAGRAPH: &str = "The minister lied about the budget to everyone.";
pub const CLAIM: &str = "The minister lied about the budget";

pub fn span(start: u32, end: u32) -> Span {
    Span {
        paragraph: 0,
        start,
        end,
    }
}

/// A valid patch for every stage, consistent with each other.
#[allow(
    clippy::too_many_lines,
    reason = "one fixture per stage, read as a table"
)]
pub fn valid_patch(stage: StageName) -> Value {
    let value = match stage {
        StageName::Extract => serde_json::to_value(ExtractPatch {
            document: Document {
                url: None,
                outlet: None,
                published_at: None,
                title: Some("Budget".into()),
                author: None,
                paragraphs: vec![PARAGRAPH.into()],
                outbound_links: vec![],
                tracking_ids: vec![],
            },
            language: Some(Language {
                code: "en".into(),
                confidence: 0.99,
                support: LanguageSupport::Evaluated,
            }),
        }),
        StageName::Understand => serde_json::to_value(UnderstandPatch {
            topic: Topic {
                summary: "Budget dispute".into(),
                entities: vec!["minister".into()],
                date: None,
                place: None,
            },
            claims: vec![Claim {
                id: "cl1".into(),
                text: CLAIM.into(),
                span: span(0, 34),
            }],
            queries: vec![SearchQuery {
                text: "minister budget".into(),
                language: "en".into(),
            }],
        }),
        StageName::Retrieve => serde_json::to_value(RetrievePatch {
            context: vec![ContextItem {
                id: "ctx1".into(),
                url: "https://news.example/budget".into(),
                outlet: Some("news.example".into()),
                published_at: Some(Utc::now()),
                title: Some("Budget row".into()),
                text: "Critics say the minister lied about the budget.".into(),
                language: Some("en".into()),
                retrieved_by: "google_news".into(),
                similarity: None,
                in_story: None,
                story_reason: None,
            }],
            detail: Some("1 source".into()),
        }),
        StageName::Story => serde_json::to_value(StoryPatch {
            assignments: vec![StoryAssignment {
                context_id: "ctx1".into(),
                similarity: 0.92,
                in_story: true,
                reason: None,
            }],
        }),
        StageName::SignalsSingle => serde_json::to_value(SignalsPatch {
            evidence: vec![evidence(
                "s1",
                Family::Tone,
                SourceRef::Document { span: span(13, 18) },
            )],
        }),
        StageName::SignalsCoordinated => serde_json::to_value(SignalsPatch {
            evidence: vec![evidence(
                "c1",
                Family::TextReuse,
                SourceRef::Context {
                    id: "ctx1".into(),
                    quote: Some("lied about the budget".into()),
                },
            )],
        }),
        StageName::Score => serde_json::to_value(ScorePatch {
            scores: Scores {
                single: Score {
                    confidence: Some(0.71),
                    abstained: false,
                    reason: None,
                    breakdown: vec![Contribution {
                        family: Family::Tone,
                        contribution: 1.2,
                        evidence_ids: vec!["s1".into()],
                    }],
                },
                coordinated: Score {
                    confidence: None,
                    abstained: true,
                    reason: Some("fewer than 3 copies".into()),
                    breakdown: vec![],
                },
            },
        }),
        StageName::Explain => serde_json::to_value(ExplainPatch {
            explanation: Explanation {
                summary: "Charged wording.".into(),
                reasons: vec![Reason {
                    text: "Uses loaded words".into(),
                    evidence_ids: vec!["s1".into()],
                }],
            },
        }),
    };
    value.expect("serializable patch")
}

fn evidence(id: &str, family: Family, source: SourceRef) -> Evidence {
    Evidence {
        id: id.into(),
        family,
        signal: "test_signal".into(),
        value: 0.8,
        detail: "detail".into(),
        source_refs: vec![source],
    }
}

/// Mounts `response` for `POST /stages/{stage}`.
pub async fn mount(worker: &MockServer, stage: StageName, response: ResponseTemplate) {
    Mock::given(method("POST"))
        .and(path(format!("/stages/{stage}")))
        .respond_with(response)
        .mount(worker)
        .await;
}

/// Mounts a valid response for every stage except those in `except`.
pub async fn mount_pipeline(worker: &MockServer, except: &[StageName]) {
    for stage in StageName::ALL {
        if !except.contains(&stage) {
            mount(
                worker,
                stage,
                ResponseTemplate::new(200).set_body_json(valid_patch(stage)),
            )
            .await;
        }
    }
}
