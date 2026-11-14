//! HTTP client for the Python stage worker (`worker/`).

use std::{collections::HashMap, time::Duration};

use junction_contracts::{Analysis, ErrorBody, StageName, StagePatch, WorkerHealth};
use reqwest::StatusCode;
use tokio::time::Instant;
use url::Url;
use uuid::Uuid;

/// Longest worker error message kept in a step's `error`.
const MAX_ERROR_CHARS: usize = 300;
/// Pause between connection attempts while the worker is restarting.
const CONNECT_RETRY: Duration = Duration::from_secs(1);

#[derive(Clone)]
pub struct WorkerClient {
    http: reqwest::Client,
    base: Url,
    connect_wait: Duration,
}

/// Result of one stage call.
#[derive(Debug)]
pub enum StageOutcome {
    Patch(StagePatch),
    /// The worker has no implementation for the stage yet (HTTP 501).
    NotImplemented,
    /// Why the stage failed, in words that are safe to show publicly.
    Failed(String),
}

impl WorkerClient {
    /// `connect_wait`: how long a stage call keeps retrying refused connections.
    pub fn new(base: Url, connect_wait: Duration) -> anyhow::Result<Self> {
        let http = reqwest::Client::builder()
            .connect_timeout(Duration::from_secs(3))
            // Below uvicorn's 5 s keep-alive, so we never reuse a connection it is closing.
            .pool_idle_timeout(Duration::from_secs(4))
            .build()?;
        Ok(Self {
            http,
            base,
            connect_wait,
        })
    }

    pub async fn run_stage(
        &self,
        stage: StageName,
        analysis: &Analysis,
        timeout: Duration,
    ) -> StageOutcome {
        let url = match self.base.join(&format!("stages/{stage}")) {
            Ok(url) => url,
            Err(e) => return StageOutcome::Failed(format!("bad worker URL: {e}")),
        };
        let started = Instant::now();
        let response = loop {
            let request = self.http.post(url.clone()).json(analysis).timeout(timeout);
            match request.send().await {
                Ok(r) => break r,
                // The worker listens only once its models are loaded: a refused connection
                // means it is restarting (deploy, out of memory), so wait for it.
                Err(e) if e.is_connect() && started.elapsed() < self.connect_wait => {
                    tokio::time::sleep(CONNECT_RETRY).await;
                }
                Err(e) if e.is_timeout() => {
                    return StageOutcome::Failed(format!("timed out after {timeout:?}"));
                }
                Err(e) => {
                    tracing::warn!(%stage, error = %e, "worker unreachable");
                    return StageOutcome::Failed("the analysis worker is unreachable".into());
                }
            }
        };
        let status = response.status();
        let body = match response.bytes().await {
            Ok(b) => b,
            Err(e) if e.is_timeout() => {
                return StageOutcome::Failed(format!("timed out after {timeout:?}"));
            }
            Err(e) => {
                tracing::warn!(%stage, error = %e, "reading the worker response failed");
                return StageOutcome::Failed("the analysis worker dropped the connection".into());
            }
        };
        match status {
            StatusCode::OK => match StagePatch::from_json(stage, &body) {
                Ok(patch) => StageOutcome::Patch(patch),
                Err(e) => {
                    StageOutcome::Failed(format!("response does not match the contract: {e}"))
                }
            },
            StatusCode::NOT_IMPLEMENTED => StageOutcome::NotImplemented,
            // The worker words its error bodies for the public; anything else (a proxy page,
            // a framework default) is not shown.
            status => StageOutcome::Failed(serde_json::from_slice::<ErrorBody>(&body).map_or_else(
                |_| format!("worker returned {status}"),
                |e| e.message.chars().take(MAX_ERROR_CHARS).collect(),
            )),
        }
    }

    /// Progress notes of the stages running for analysis `id`; empty when there are none or
    /// the worker does not answer.
    pub async fn progress(&self, id: Uuid) -> HashMap<StageName, String> {
        let notes = async {
            let url = self.base.join(&format!("progress/{id}")).ok()?;
            let request = self.http.get(url).timeout(Duration::from_secs(1));
            let response = request.send().await.ok()?;
            response.error_for_status().ok()?.json().await.ok()
        };
        notes.await.unwrap_or_default()
    }

    /// The worker's health, or `None` when it is unreachable or answers garbage.
    pub async fn health(&self) -> Option<WorkerHealth> {
        let url = self.base.join("health").ok()?;
        let response = self
            .http
            .get(url)
            .timeout(Duration::from_secs(2))
            .send()
            .await
            .ok()?;
        response.error_for_status().ok()?.json().await.ok()
    }
}
