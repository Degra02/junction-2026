//! Public API of the propaganda-analysis pipeline.
//!
//! The binary (`main.rs`) only parses the command line; everything else lives here so tests
//! can build the same [`app`] the server runs.

pub mod config;
pub mod db;
pub mod error;
pub mod events;
pub mod pipeline;
pub mod ratelimit;
pub mod routes;
pub mod worker;

use std::{net::SocketAddr, sync::Arc};

use anyhow::Context as _;
use axum::Router;
use tokio::net::TcpListener;
use tokio_util::sync::CancellationToken;

use crate::{
    config::Config, db::Db, events::Hub, pipeline::Pipeline, ratelimit::RateLimiter,
    worker::WorkerClient,
};

/// Shared handles for request handlers.
#[derive(Clone)]
pub struct AppState {
    pub config: Arc<Config>,
    pub db: Db,
    pub hub: Hub,
    pub pipeline: Pipeline,
    pub worker: WorkerClient,
    pub rate_limiter: RateLimiter,
    /// Cancelled on shutdown; ends open SSE streams so the server can drain.
    pub shutdown: CancellationToken,
}

impl AppState {
    /// Opens the database, marks analyses interrupted by a restart, wires the pipeline.
    pub async fn new(config: Config) -> anyhow::Result<Self> {
        let db = Db::open(&config.database_path).await?;
        let hub = Hub::default();
        let worker = WorkerClient::new(config.worker_url.clone(), config.stage_timeout)?;
        let pipeline = Pipeline::new(
            db.clone(),
            worker.clone(),
            hub.clone(),
            config.max_concurrent_analyses,
        );
        let interrupted = pipeline.recover().await?;
        if interrupted > 0 {
            tracing::warn!(
                interrupted,
                "marked analyses interrupted by a restart as failed"
            );
        }
        Ok(Self {
            rate_limiter: RateLimiter::new(config.rate_limit_per_minute, config.trust_proxy),
            config: Arc::new(config),
            db,
            hub,
            pipeline,
            worker,
            shutdown: CancellationToken::new(),
        })
    }
}

/// The full HTTP application.
pub fn app(state: AppState) -> Router {
    routes::router(state)
}

/// Serves on `listener` until `shutdown` is cancelled, then drains connections.
pub async fn serve(listener: TcpListener, state: AppState) -> anyhow::Result<()> {
    let shutdown = state.shutdown.clone();
    let app = app(state).into_make_service_with_connect_info::<SocketAddr>();
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown.cancelled_owned())
        .await
        .context("serving HTTP")
}
