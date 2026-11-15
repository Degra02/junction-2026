//! Public API of the propaganda-analysis pipeline.
//!
//! The binary (`main.rs`) only parses the command line; everything else lives here so tests
//! can build the same [`app`] the server runs.

pub mod config;
pub mod db;
pub mod error;
pub mod events;
pub mod graph;
pub mod pipeline;
pub mod ratelimit;
pub mod routes;
pub mod worker;

use std::{net::SocketAddr, path::PathBuf, sync::Arc, time::Duration};

use anyhow::Context as _;
use axum::Router;
use tokio::net::TcpListener;
use tokio_util::sync::CancellationToken;

use crate::{
    config::Config, db::Db, events::Hub, pipeline::Pipeline, ratelimit::RateLimiter,
    worker::WorkerClient,
};

/// Database copies kept in `backups/`.
const BACKUPS_KEPT: usize = 4;

/// Shared handles for request handlers.
#[derive(Clone)]
pub struct AppState {
    pub config: Arc<Config>,
    pub db: Db,
    pub hub: Hub,
    pub pipeline: Pipeline,
    pub worker: WorkerClient,
    pub rate_limiter: RateLimiter,
    /// Held while a submission looks up the cache and inserts, so two identical submissions
    /// arriving together do not both run.
    pub create_lock: Arc<tokio::sync::Mutex<()>>,
    /// Cancelled on shutdown; ends open SSE streams so the server can drain.
    pub shutdown: CancellationToken,
}

impl AppState {
    /// Opens the database, marks analyses interrupted by a restart, wires the pipeline.
    pub async fn new(config: Config) -> anyhow::Result<Self> {
        let db = Db::open(&config.database_path).await?;
        let hub = Hub::default();
        let worker = WorkerClient::new(config.worker_url.clone(), config.worker_connect_wait)?;
        let pipeline = Pipeline::new(db.clone(), worker.clone(), hub.clone(), &config);
        let interrupted = pipeline.recover().await?;
        if interrupted > 0 {
            tracing::warn!(
                interrupted,
                "marked analyses interrupted by a restart as failed"
            );
        }
        Ok(Self {
            rate_limiter: RateLimiter::new(
                config.rate_limit_per_minute,
                config.max_analyses_per_hour,
                config.trust_proxy,
            ),
            config: Arc::new(config),
            db,
            hub,
            pipeline,
            worker,
            create_lock: Arc::default(),
            shutdown: CancellationToken::new(),
        })
    }

    /// Where the periodic database copies go: `backups/` next to the database.
    pub fn backup_dir(&self) -> PathBuf {
        self.config.database_path.with_file_name("backups")
    }
}

/// The full HTTP application.
pub fn app(state: AppState) -> Router {
    routes::router(state)
}

/// Serves on `listener` until `shutdown` is cancelled, then drains connections.
pub async fn serve(listener: TcpListener, state: AppState) -> anyhow::Result<()> {
    let shutdown = state.shutdown.clone();
    if !state.config.backup_interval.is_zero() {
        tokio::spawn(backups(state.clone(), state.config.backup_interval));
    }
    let app = app(state).into_make_service_with_connect_info::<SocketAddr>();
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown.cancelled_owned())
        .await
        .context("serving HTTP")
}

/// Copies the database every `every` until shutdown. A consistent copy survives a bad
/// migration or a corrupted file; it sits on the same disk, so it is no off-site backup.
async fn backups(state: AppState, every: Duration) {
    let mut tick = tokio::time::interval_at(tokio::time::Instant::now() + every, every);
    loop {
        tokio::select! {
            () = state.shutdown.cancelled() => return,
            _ = tick.tick() => match state.db.backup(&state.backup_dir(), BACKUPS_KEPT).await {
                Ok(path) => tracing::info!(path = %path.display(), "database backed up"),
                Err(e) => tracing::error!(error = ?e, "database backup failed"),
            },
        }
    }
}
