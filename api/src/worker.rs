//! HTTP client for the Python stage worker (`worker/`).

use std::time::Duration;

use junction_contracts::{Analysis, StageName, StagePatch, WorkerHealth};
use reqwest::StatusCode;
use url::Url;

/// Longest worker error body kept in a step's `error`.
const MAX_ERROR_CHARS: usize = 300;

#[derive(Clone)]
pub struct WorkerClient {
    http: reqwest::Client,
    base: Url,
    stage_timeout: Duration,
}

/// Result of one stage call.
#[derive(Debug)]
pub enum StageOutcome {
    Patch(StagePatch),
    /// The worker has no implementation for the stage yet (HTTP 501).
    NotImplemented,
    Failed(String),
}

impl WorkerClient {
    pub fn new(base: Url, stage_timeout: Duration) -> anyhow::Result<Self> {
        let http = reqwest::Client::builder()
            .connect_timeout(Duration::from_secs(3))
            // Below uvicorn's 5 s keep-alive, so we never reuse a connection it is closing.
            .pool_idle_timeout(Duration::from_secs(4))
            .build()?;
        Ok(Self {
            http,
            base,
            stage_timeout,
        })
    }

    pub async fn run_stage(&self, stage: StageName, analysis: &Analysis) -> StageOutcome {
        let url = match self.base.join(&format!("stages/{stage}")) {
            Ok(url) => url,
            Err(e) => return StageOutcome::Failed(format!("bad worker URL: {e}")),
        };
        let response = match self
            .http
            .post(url)
            .json(analysis)
            .timeout(self.stage_timeout)
            .send()
            .await
        {
            Ok(r) => r,
            Err(e) if e.is_timeout() => {
                return StageOutcome::Failed(format!("timed out after {:?}", self.stage_timeout));
            }
            Err(e) => return StageOutcome::Failed(format!("worker unreachable: {e}")),
        };
        let status = response.status();
        let body = match response.bytes().await {
            Ok(b) => b,
            Err(e) => return StageOutcome::Failed(format!("reading worker response: {e}")),
        };
        match status {
            StatusCode::OK => match StagePatch::from_json(stage, &body) {
                Ok(patch) => StageOutcome::Patch(patch),
                Err(e) => {
                    StageOutcome::Failed(format!("response does not match the contract: {e}"))
                }
            },
            StatusCode::NOT_IMPLEMENTED => StageOutcome::NotImplemented,
            status => {
                let text: String = String::from_utf8_lossy(&body)
                    .chars()
                    .take(MAX_ERROR_CHARS)
                    .collect();
                StageOutcome::Failed(format!("worker returned {status}: {text}"))
            }
        }
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
