//! The data contract shared by the API, the Python worker and the web UI.
//!
//! Rust types here are the single source of truth. `mise run contracts` turns them into
//! `contracts/openapi.json`, the pydantic models in `pipeline/common/contracts.py` and the
//! TypeScript types in `contracts/ts/api.d.ts`.
//!
//! Every pipeline stage receives the whole [`Analysis`] and returns a [`StagePatch`] that
//! touches only the fields that stage owns. [`Analysis::apply`] validates and merges it.

mod analysis;
mod api;
mod apply;
mod stage;

pub use analysis::*;
pub use api::*;
pub use apply::{ApplyError, ApplyReport};
pub use stage::*;

/// Bumped on every breaking change to [`Analysis`] or the stage patches.
pub const SCHEMA_VERSION: u32 = 1;
