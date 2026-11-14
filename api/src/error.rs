//! Every non-2xx response is JSON [`ErrorBody`].

use axum::{
    Json,
    extract::{
        FromRequest, FromRequestParts,
        rejection::{JsonRejection, PathRejection},
    },
    http::StatusCode,
    response::{IntoResponse, Response},
};
use junction_contracts::ErrorBody;

/// `axum::Json` whose rejections are JSON [`ErrorBody`] responses.
#[derive(FromRequest)]
#[from_request(via(axum::Json), rejection(ApiError))]
pub struct ApiJson<T>(pub T);

/// `axum::extract::Path` whose rejections are JSON [`ErrorBody`] responses.
#[derive(FromRequestParts)]
#[from_request(via(axum::extract::Path), rejection(ApiError))]
pub struct ApiPath<T>(pub T);

#[derive(Debug, thiserror::Error)]
pub enum ApiError {
    #[error("{0}")]
    InvalidInput(String),
    #[error("{0}")]
    NotFound(String),
    #[error("too many new analyses from this address; try again in a minute")]
    RateLimited,
    #[error("service unavailable: {0}")]
    Unavailable(String),
    #[error(transparent)]
    Internal(#[from] anyhow::Error),
}

impl From<sqlx::Error> for ApiError {
    fn from(e: sqlx::Error) -> Self {
        Self::Internal(e.into())
    }
}

impl From<JsonRejection> for ApiError {
    fn from(e: JsonRejection) -> Self {
        Self::InvalidInput(e.body_text())
    }
}

impl From<PathRejection> for ApiError {
    fn from(e: PathRejection) -> Self {
        Self::NotFound(e.body_text())
    }
}

impl ApiError {
    const fn status_and_code(&self) -> (StatusCode, &'static str) {
        match self {
            Self::InvalidInput(_) => (StatusCode::UNPROCESSABLE_ENTITY, "invalid_input"),
            Self::NotFound(_) => (StatusCode::NOT_FOUND, "not_found"),
            Self::RateLimited => (StatusCode::TOO_MANY_REQUESTS, "rate_limited"),
            Self::Unavailable(_) => (StatusCode::SERVICE_UNAVAILABLE, "unavailable"),
            Self::Internal(_) => (StatusCode::INTERNAL_SERVER_ERROR, "internal"),
        }
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let (status, code) = self.status_and_code();
        let message = if let Self::Internal(e) = &self {
            tracing::error!(error = ?e, "internal error");
            "internal error; see the server logs".to_owned()
        } else {
            self.to_string()
        };
        let body = ErrorBody {
            error: code.to_owned(),
            message,
        };
        (status, Json(body)).into_response()
    }
}
