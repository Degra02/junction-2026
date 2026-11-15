//! SQLite persistence of [`Analysis`] records (WAL, one JSON record per row).

use std::{
    path::{Path, PathBuf},
    str::FromStr as _,
    time::Duration,
};

use anyhow::Context as _;
use chrono::Utc;
use junction_contracts::{Analysis, AnalysisStatus, GraphPatch, Step};
use sqlx::{
    SqlitePool,
    sqlite::{SqliteConnectOptions, SqliteJournalMode, SqlitePoolOptions, SqliteSynchronous},
    types::Json,
};
use uuid::Uuid;

static MIGRATOR: sqlx::migrate::Migrator = sqlx::migrate!("./migrations");

#[derive(Clone)]
pub struct Db {
    pool: SqlitePool,
}

/// What `GET /api/stats` aggregates from one analysis.
pub struct StatRow {
    pub status: String,
    pub created_at: String,
    pub updated_at: String,
    pub steps: Vec<Step>,
}

impl Db {
    /// Opens (creating if needed) the database at `path` and runs the migrations.
    pub async fn open(path: &Path) -> anyhow::Result<Self> {
        if let Some(dir) = path.parent().filter(|d| !d.as_os_str().is_empty()) {
            std::fs::create_dir_all(dir).with_context(|| format!("creating {}", dir.display()))?;
        }
        let options = SqliteConnectOptions::from_str("sqlite:")?
            .filename(path)
            .create_if_missing(true)
            .journal_mode(SqliteJournalMode::Wal)
            .synchronous(SqliteSynchronous::Normal)
            .busy_timeout(Duration::from_secs(5))
            .foreign_keys(true);
        let pool = SqlitePoolOptions::new()
            .max_connections(4)
            .connect_with(options)
            .await
            .with_context(|| format!("opening {}", path.display()))?;
        MIGRATOR.run(&pool).await.context("running migrations")?;
        Ok(Self { pool })
    }
    pub const fn pool(&self) -> &SqlitePool {
        &self.pool
    }

    pub async fn ping(&self) -> sqlx::Result<()> {
        sqlx::query("SELECT 1").execute(&self.pool).await.map(drop)
    }

    pub async fn ingest_graph(&self, analysis: &Analysis, patch: &GraphPatch) -> sqlx::Result<()> {
        crate::graph::ingest_patch(&self.pool, analysis, patch).await
    }

    pub async fn insert(&self, analysis: &Analysis, input_hash: &str) -> sqlx::Result<()> {
        sqlx::query(
            "INSERT INTO analyses (id, input_hash, status, created_at, updated_at, record) \
             VALUES (?, ?, ?, ?, ?, ?)",
        )
        .bind(analysis.id.to_string())
        .bind(input_hash)
        .bind(status_str(analysis.status))
        .bind(analysis.created_at.to_rfc3339())
        .bind(analysis.updated_at.to_rfc3339())
        .bind(Json(analysis))
        .execute(&self.pool)
        .await
        .map(drop)
    }

    pub async fn save(&self, analysis: &Analysis) -> sqlx::Result<()> {
        sqlx::query("UPDATE analyses SET status = ?, updated_at = ?, record = ? WHERE id = ?")
            .bind(status_str(analysis.status))
            .bind(analysis.updated_at.to_rfc3339())
            .bind(Json(analysis))
            .bind(analysis.id.to_string())
            .execute(&self.pool)
            .await
            .map(drop)
    }

    pub async fn get(&self, id: Uuid) -> sqlx::Result<Option<Analysis>> {
        let row: Option<(Json<Analysis>,)> =
            sqlx::query_as("SELECT record FROM analyses WHERE id = ?")
                .bind(id.to_string())
                .fetch_optional(&self.pool)
                .await?;
        Ok(row.map(|(record,)| record.0))
    }

    /// Latest analysis of the same input that is still in progress or finished without a failed
    /// step. A result degraded by a transient failure (a throttled source, an LLM timeout) is
    /// not reused: the next submission runs again.
    pub async fn find_reusable(&self, input_hash: &str) -> sqlx::Result<Option<Uuid>> {
        let row: Option<(String,)> = sqlx::query_as(
            "SELECT id FROM analyses WHERE input_hash = ? AND status <> 'failed' \
             AND NOT EXISTS ( \
                 SELECT 1 FROM json_each(analyses.record, '$.steps') AS step \
                 WHERE json_extract(step.value, '$.state') = 'failed' \
                   AND json_extract(step.value, '$.name') <> 'graph') \
             ORDER BY created_at DESC LIMIT 1",
        )
        .bind(input_hash)
        .fetch_optional(&self.pool)
        .await?;
        Ok(row.and_then(|(id,)| Uuid::parse_str(&id).ok()))
    }

    /// Analyses that were queued or running when the process stopped.
    pub async fn unfinished(&self) -> sqlx::Result<Vec<Analysis>> {
        let rows: Vec<(Json<Analysis>,)> =
            sqlx::query_as("SELECT record FROM analyses WHERE status IN ('queued', 'running')")
                .fetch_all(&self.pool)
                .await?;
        Ok(rows.into_iter().map(|(record,)| record.0).collect())
    }

    /// Finished analyses in chronological order, for replaying the graph stage.
    pub async fn finished_analyses(&self) -> sqlx::Result<Vec<Analysis>> {
        let rows: Vec<(Json<Analysis>,)> = sqlx::query_as(
            "SELECT record FROM analyses WHERE status = 'done' ORDER BY created_at ASC",
        )
        .fetch_all(&self.pool)
        .await?;
        Ok(rows.into_iter().map(|(record,)| record.0).collect())
    }

    /// Counts an accepted submission, and whether an earlier analysis answered it.
    pub async fn count_submission(&self, cache_hit: bool) -> sqlx::Result<()> {
        sqlx::query(
            "UPDATE counters SET value = value + 1 \
             WHERE name = 'submissions' OR (name = 'cache_hits' AND ?)",
        )
        .bind(cache_hit)
        .execute(&self.pool)
        .await
        .map(drop)
    }

    /// `(submissions, cache_hits)` since the database was created.
    pub async fn submission_counts(&self) -> sqlx::Result<(u64, u64)> {
        let rows: Vec<(String, i64)> = sqlx::query_as("SELECT name, value FROM counters")
            .fetch_all(&self.pool)
            .await?;
        let value = |name: &str| {
            let found = rows.iter().find(|(n, _)| n == name);
            found.map_or(0, |(_, v)| u64::try_from(*v).unwrap_or(0))
        };
        Ok((value("submissions"), value("cache_hits")))
    }

    /// Status, timestamps and steps of every analysis.
    pub async fn stat_rows(&self) -> sqlx::Result<Vec<StatRow>> {
        let rows: Vec<(String, String, String, Json<Vec<Step>>)> = sqlx::query_as(
            "SELECT status, created_at, updated_at, json_extract(record, '$.steps') FROM analyses",
        )
        .fetch_all(&self.pool)
        .await?;
        let rows = rows.into_iter();
        Ok(rows
            .map(|(status, created_at, updated_at, steps)| StatRow {
                status,
                created_at,
                updated_at,
                steps: steps.0,
            })
            .collect())
    }

    /// Writes a consistent copy of the live database into `dir` and keeps the newest `keep`.
    pub async fn backup(&self, dir: &Path, keep: usize) -> anyhow::Result<PathBuf> {
        std::fs::create_dir_all(dir).with_context(|| format!("creating {}", dir.display()))?;
        let name = format!("app-{}.db", Utc::now().format("%Y%m%dT%H%M%S%3fZ"));
        let path = dir.join(name);
        sqlx::query("VACUUM INTO ?")
            .bind(path.to_string_lossy().into_owned())
            .execute(&self.pool)
            .await
            .with_context(|| format!("writing {}", path.display()))?;

        let mut copies: Vec<PathBuf> = std::fs::read_dir(dir)?
            .filter_map(|entry| Some(entry.ok()?.path()))
            .filter(|p| p.extension().is_some_and(|e| e == "db"))
            .collect();
        // The timestamp in the name sorts chronologically.
        copies.sort();
        for old in copies.iter().rev().skip(keep) {
            std::fs::remove_file(old).with_context(|| format!("removing {}", old.display()))?;
        }
        Ok(path)
    }
}

const fn status_str(status: AnalysisStatus) -> &'static str {
    match status {
        AnalysisStatus::Queued => "queued",
        AnalysisStatus::Running => "running",
        AnalysisStatus::Done => "done",
        AnalysisStatus::Failed => "failed",
    }
}
