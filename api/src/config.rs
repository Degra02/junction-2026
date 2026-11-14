//! Runtime configuration from environment variables (loaded from `.env` by mise).

use std::{net::SocketAddr, path::PathBuf, str::FromStr, time::Duration};

use anyhow::Context;
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
    /// `MAX_CONCURRENT_ANALYSES`, default 1: the 2 vCPU VPS runs one pipeline at a time.
    pub max_concurrent_analyses: usize,
    /// `MAX_INPUT_CHARS`, default 50 000.
    pub max_input_chars: usize,
    /// `RATE_LIMIT_PER_MINUTE` new analyses per client IP, default 10; 0 disables.
    pub rate_limit_per_minute: u32,
    /// `TRUST_PROXY`, default false. True only behind Caddy: the client IP is then the last
    /// `X-Forwarded-For` entry.
    pub trust_proxy: bool,
    /// `METRICS_PATH`, default `evals/results/metrics.json` (written by the eval harness).
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
            max_concurrent_analyses: var("MAX_CONCURRENT_ANALYSES", "1")?,
            max_input_chars: var("MAX_INPUT_CHARS", "50000")?,
            rate_limit_per_minute: var("RATE_LIMIT_PER_MINUTE", "10")?,
            trust_proxy: var("TRUST_PROXY", "false")?,
            metrics_path: var("METRICS_PATH", "evals/results/metrics.json")?,
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
