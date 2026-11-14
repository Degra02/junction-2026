//! Runtime configuration from environment variables (loaded from `.env` by mise).

use std::{net::SocketAddr, path::PathBuf, str::FromStr, time::Duration};

use anyhow::Context;
use junction_contracts::StageName;
use url::Url;

#[derive(Debug, Clone)]
pub struct Config {
    /// `API_ADDR`, default `127.0.0.1:8080`.
    pub addr: SocketAddr,
    /// `DATABASE_PATH`, default `data/app.db`.
    pub database_path: PathBuf,
    /// `WORKER_URL`, default `http://127.0.0.1:8001`.
    pub worker_url: Url,
    /// `STAGE_TIMEOUT_SECS`, default 120.
    pub stage_timeout: Duration,
    /// `ANALYSIS_TIMEOUT_SECS`, default 300: once spent, the remaining stages are skipped.
    pub analysis_timeout: Duration,
    /// `WORKER_CONNECT_WAIT_SECS`, default 0: how long a stage call keeps retrying while the
    /// worker refuses connections. The worker listens only once its models are loaded, so in
    /// production this covers its restart after a deploy.
    pub worker_connect_wait: Duration,
    /// `MAX_CONCURRENT_ANALYSES`, default 4: analyses past this wait in the queue.
    pub max_concurrent_analyses: usize,
    /// `MAX_CONCURRENT_INFERENCE`, default 1: model stages (story, signals) running at once
    /// across all analyses. The 2 vCPU VPS runs one inference at a time.
    pub max_concurrent_inference: usize,
    /// `MAX_INPUT_CHARS`, default 50 000.
    pub max_input_chars: usize,
    /// `RATE_LIMIT_PER_MINUTE` new analyses per client address, default 30; 0 disables.
    /// Cached results do not count.
    pub rate_limit_per_minute: u32,
    /// `MAX_ANALYSES_PER_HOUR` new analyses from all clients together, default 600; 0 disables.
    /// Caps LLM and scraping spend whatever the number of client addresses.
    pub max_analyses_per_hour: u32,
    /// `TRUST_PROXY`, default false. True only behind Caddy: the client IP is then the last
    /// `X-Forwarded-For` entry.
    pub trust_proxy: bool,
    /// `STAGES_DISABLED`, comma-separated stage names, default none: these stages are skipped
    /// without calling the worker (kill switch for a stage that misbehaves during the demo).
    pub stages_disabled: Vec<StageName>,
    /// `BACKUP_INTERVAL_MINS`, default 0 (off): how often a copy of the database is written to
    /// `backups/` next to it.
    pub backup_interval: Duration,
    /// `METRICS_PATH`, default `evals/metrics.json` (committed, written by the eval harness).
    pub metrics_path: PathBuf,
    /// `PIPELINE_VERSION`, default `dev`. Part of the cache key.
    pub pipeline_version: String,
}

impl Config {
    pub fn from_env() -> anyhow::Result<Self> {
        Ok(Self {
            addr: var("API_ADDR", "127.0.0.1:8080")?,
            database_path: var("DATABASE_PATH", "data/app.db")?,
            worker_url: var("WORKER_URL", "http://127.0.0.1:8001")?,
            stage_timeout: Duration::from_secs(var("STAGE_TIMEOUT_SECS", "120")?),
            analysis_timeout: Duration::from_secs(var("ANALYSIS_TIMEOUT_SECS", "300")?),
            worker_connect_wait: Duration::from_secs(var("WORKER_CONNECT_WAIT_SECS", "0")?),
            max_concurrent_analyses: var("MAX_CONCURRENT_ANALYSES", "4")?,
            max_concurrent_inference: var("MAX_CONCURRENT_INFERENCE", "1")?,
            max_input_chars: var("MAX_INPUT_CHARS", "50000")?,
            rate_limit_per_minute: var("RATE_LIMIT_PER_MINUTE", "30")?,
            max_analyses_per_hour: var("MAX_ANALYSES_PER_HOUR", "600")?,
            trust_proxy: var("TRUST_PROXY", "false")?,
            stages_disabled: stages(&var::<String>("STAGES_DISABLED", "")?)?,
            backup_interval: Duration::from_secs(60 * var::<u64>("BACKUP_INTERVAL_MINS", "0")?),
            metrics_path: var("METRICS_PATH", "evals/metrics.json")?,
            pipeline_version: var("PIPELINE_VERSION", "dev")?,
        })
    }
}

/// Reads `name`, treating an empty value (blank line in `.env`) as unset.
fn var<T>(name: &str, default: &str) -> anyhow::Result<T>
where
    T: FromStr,
    T::Err: std::error::Error + Send + Sync + 'static,
{
    let raw = std::env::var(name).ok().filter(|v| !v.trim().is_empty());
    let value = raw.as_deref().unwrap_or(default);
    value
        .trim()
        .parse()
        .with_context(|| format!("invalid {name}={value:?}"))
}

/// Parses a comma-separated list of stage names.
pub fn stages(list: &str) -> anyhow::Result<Vec<StageName>> {
    list.split(',')
        .map(str::trim)
        .filter(|name| !name.is_empty())
        .map(|name| name.parse().map_err(anyhow::Error::msg))
        .collect()
}
