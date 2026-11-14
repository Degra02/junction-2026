//! Per-client-IP limit on new analyses: protects LLM and scraping spend on the public URL.

use std::{
    net::{IpAddr, SocketAddr},
    num::NonZeroU32,
    sync::Arc,
};

use axum::{
    extract::{ConnectInfo, Request, State},
    http::HeaderMap,
    middleware::Next,
    response::{IntoResponse, Response},
};
use governor::{DefaultKeyedRateLimiter, Quota, RateLimiter as Governor};

use crate::error::ApiError;

#[derive(Clone)]
pub struct RateLimiter {
    limiter: Option<Arc<DefaultKeyedRateLimiter<IpAddr>>>,
    trust_proxy: bool,
}

impl RateLimiter {
    /// `per_minute == 0` disables the limit.
    pub fn new(per_minute: u32, trust_proxy: bool) -> Self {
        let limiter =
            NonZeroU32::new(per_minute).map(|n| Arc::new(Governor::keyed(Quota::per_minute(n))));
        Self {
            limiter,
            trust_proxy,
        }
    }

    /// Client address: the last `X-Forwarded-For` hop when behind our proxy (Caddy replaces
    /// untrusted forwarded headers with the real peer), otherwise the TCP peer.
    fn client_ip(&self, headers: &HeaderMap, peer: Option<SocketAddr>) -> Option<IpAddr> {
        let forwarded = self
            .trust_proxy
            .then(|| headers.get("x-forwarded-for")?.to_str().ok())
            .flatten()
            .and_then(|v| v.rsplit(',').next())
            .and_then(|ip| ip.trim().parse().ok());
        forwarded.or_else(|| peer.map(|p| p.ip()))
    }
}

pub async fn limit(State(rl): State<RateLimiter>, request: Request, next: Next) -> Response {
    if let Some(limiter) = &rl.limiter {
        let peer = request
            .extensions()
            .get::<ConnectInfo<SocketAddr>>()
            .map(|c| c.0);
        if let Some(ip) = rl.client_ip(request.headers(), peer) {
            if limiter.check_key(&ip).is_err() {
                return ApiError::RateLimited.into_response();
            }
            if limiter.len() > 10_000 {
                limiter.retain_recent();
            }
        }
    }
    next.run(request).await
}
