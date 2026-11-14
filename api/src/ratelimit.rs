//! Limits on new analyses: per client address and for the whole service. They protect LLM and
//! scraping spend on the public URL; cached results and reads are never limited.

use std::{
    convert::Infallible,
    net::{IpAddr, Ipv6Addr, SocketAddr},
    num::NonZeroU32,
    sync::Arc,
};

use axum::{
    extract::{ConnectInfo, FromRequestParts},
    http::{HeaderMap, request::Parts},
};
use governor::{DefaultDirectRateLimiter, DefaultKeyedRateLimiter, Quota, RateLimiter as Governor};

use crate::{AppState, error::ApiError};

#[derive(Clone)]
pub struct RateLimiter {
    per_client: Option<Arc<DefaultKeyedRateLimiter<IpAddr>>>,
    global: Option<Arc<DefaultDirectRateLimiter>>,
    trust_proxy: bool,
}

impl RateLimiter {
    /// `per_minute` new analyses per client and `per_hour` in total; 0 disables either limit.
    pub fn new(per_minute: u32, per_hour: u32, trust_proxy: bool) -> Self {
        let per_client =
            NonZeroU32::new(per_minute).map(|n| Arc::new(Governor::keyed(Quota::per_minute(n))));
        let global =
            NonZeroU32::new(per_hour).map(|n| Arc::new(Governor::direct(Quota::per_hour(n))));
        Self {
            per_client,
            global,
            trust_proxy,
        }
    }

    /// Spends one new analysis from the client's budget and from the service's.
    pub fn check(&self, client: Option<IpAddr>) -> Result<(), ApiError> {
        if let (Some(limiter), Some(ip)) = (&self.per_client, client) {
            if limiter.check_key(&bucket(ip)).is_err() {
                return Err(ApiError::RateLimited);
            }
            if limiter.len() > 10_000 {
                limiter.retain_recent();
            }
        }
        if self.global.as_ref().is_some_and(|g| g.check().is_err()) {
            return Err(ApiError::Busy);
        }
        Ok(())
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

/// The key a client is limited by: its IPv4 address, or its IPv6 /64 (one subscriber owns the
/// whole prefix and can rotate through it freely).
fn bucket(ip: IpAddr) -> IpAddr {
    match ip.to_canonical() {
        IpAddr::V6(v6) => {
            let s = v6.segments();
            IpAddr::V6(Ipv6Addr::new(s[0], s[1], s[2], s[3], 0, 0, 0, 0))
        }
        v4 @ IpAddr::V4(_) => v4,
    }
}

/// Extractor for the address new analyses are limited by; `None` when it is unknown.
pub struct ClientIp(pub Option<IpAddr>);

impl FromRequestParts<AppState> for ClientIp {
    type Rejection = Infallible;

    fn from_request_parts(
        parts: &mut Parts,
        state: &AppState,
    ) -> impl Future<Output = Result<Self, Infallible>> + Send {
        let peer = parts.extensions.get::<ConnectInfo<SocketAddr>>();
        let peer = peer.map(|connect| connect.0);
        let client = state.rate_limiter.client_ip(&parts.headers, peer);
        std::future::ready(Ok(Self(client)))
    }
}
