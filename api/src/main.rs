//! `junction-api [serve|openapi|healthcheck|replay-graph]`
//!
//! - `serve` (default): run the HTTP server.
//! - `openapi`: print the OpenAPI document (`mise run contracts` writes it to `contracts/`).
//! - `healthcheck`: exit 0 when the local server answers `/api/health`; used by Docker, whose
//!   distroless image has no curl.
//! - `replay-graph`: replay every finished stored analysis through `POST /stages/graph` and
//!   ingest its observations into SQLite.

use std::process::ExitCode;

use anyhow::Context as _;
use junction_api::{
    AppState, config::Config, db::Db, routes, serve, worker::StageOutcome, worker::WorkerClient,
};
use junction_contracts::{StageName, StagePatch};
use tokio::net::TcpListener;
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> anyhow::Result<ExitCode> {
    match std::env::args().nth(1).as_deref() {
        None | Some("serve") => run().await.map(|()| ExitCode::SUCCESS),
        Some("openapi") => {
            println!("{}", routes::openapi().to_pretty_json()?);
            Ok(ExitCode::SUCCESS)
        }
        Some("healthcheck") => Ok(healthcheck().await),
        Some("replay-graph") => replay_graph().await.map(|()| ExitCode::SUCCESS),
        Some(other) => {
            eprintln!(
                "unknown command {other:?}; expected serve, openapi, healthcheck or replay-graph"
            );
            Ok(ExitCode::from(2))
        }
    }
}

async fn run() -> anyhow::Result<()> {
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info,tower_http=info,sqlx=warn"));
    let logs = tracing_subscriber::fmt().with_env_filter(filter);
    if std::env::var("LOG_FORMAT").is_ok_and(|f| f == "json") {
        logs.json().init();
    } else {
        logs.init();
    }

    let config = Config::from_env()?;
    let listener = TcpListener::bind(config.addr)
        .await
        .with_context(|| format!("binding {}", config.addr))?;
    let state = AppState::new(config).await?;
    tracing::info!(addr = %listener.local_addr()?, "listening");

    let shutdown = state.shutdown.clone();
    tokio::spawn(async move {
        shutdown_signal().await;
        tracing::info!("shutting down");
        shutdown.cancel();
    });
    serve(listener, state).await
}

async fn shutdown_signal() {
    let ctrl_c = tokio::signal::ctrl_c();
    #[cfg(unix)]
    {
        let mut term = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("installing the SIGTERM handler");
        tokio::select! {
            _ = ctrl_c => {}
            _ = term.recv() => {}
        }
    }
    #[cfg(not(unix))]
    let _ = ctrl_c.await;
}

async fn healthcheck() -> ExitCode {
    let addr =
        Config::from_env().map_or_else(|_| "127.0.0.1:8080".parse().expect("valid"), |c| c.addr);
    let port = addr.port();
    let url = format!("http://127.0.0.1:{port}/api/health");
    match reqwest::get(&url)
        .await
        .and_then(reqwest::Response::error_for_status)
    {
        Ok(_) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("healthcheck {url}: {e}");
            ExitCode::FAILURE
        }
    }
}

async fn replay_graph() -> anyhow::Result<()> {
    let config = Config::from_env()?;
    let db = Db::open(&config.database_path).await?;
    let worker = WorkerClient::new(config.worker_url.clone(), config.worker_connect_wait)?;
    let analyses = db.finished_analyses().await?;
    let total = analyses.len();
    let mut ingested = 0usize;
    for mut analysis in analyses {
        match worker
            .run_stage(StageName::Graph, &analysis, config.stage_timeout)
            .await
        {
            StageOutcome::Patch(patch) => {
                let gp = match &patch {
                    StagePatch::Graph(gp) => gp.clone(),
                    _ => continue,
                };
                if let Err(e) = analysis.apply(patch) {
                    eprintln!("skipping {}: rejected by contract ({e})", analysis.id);
                    continue;
                }
                db.ingest_graph(&analysis, &gp).await?;
                ingested += 1;
            }
            StageOutcome::NotImplemented => {
                anyhow::bail!("worker does not implement the `graph` stage yet");
            }
            StageOutcome::Failed(err) => {
                eprintln!("skipping {}: worker failed ({err})", analysis.id);
            }
        }
    }
    println!("replayed {ingested} of {total} finished analyses into SQLite graph tables");
    Ok(())
}
