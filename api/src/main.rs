//! `junction-api [serve|openapi|healthcheck]`
//!
//! - `serve` (default): run the HTTP server.
//! - `openapi`: print the OpenAPI document (`mise run contracts` writes it to `contracts/`).
//! - `healthcheck`: exit 0 when the local server answers `/api/health`; used by Docker, whose
//!   distroless image has no curl.

use std::process::ExitCode;

use anyhow::Context as _;
use junction_api::{AppState, config::Config, routes, serve};
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
        Some(other) => {
            eprintln!("unknown command {other:?}; expected serve, openapi or healthcheck");
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
