//! SQLite persistence of [`Analysis`] records (WAL, one JSON record per row).

use std::{path::Path, str::FromStr as _, time::Duration};

use anyhow::Context as _;
use junction_contracts::{Analysis, AnalysisStatus};
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

    pub async fn ping(&self) -> sqlx::Result<()> {
        sqlx::query("SELECT 1").execute(&self.pool).await.map(drop)
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

    /// Latest analysis of the same input that is running or succeeded; failed ones are retried.
    pub async fn find_reusable(&self, input_hash: &str) -> sqlx::Result<Option<Uuid>> {
        let row: Option<(String,)> = sqlx::query_as(
            "SELECT id FROM analyses WHERE input_hash = ? AND status <> 'failed' \
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
}

const fn status_str(status: AnalysisStatus) -> &'static str {
    match status {
        AnalysisStatus::Queued => "queued",
        AnalysisStatus::Running => "running",
        AnalysisStatus::Done => "done",
        AnalysisStatus::Failed => "failed",
    }
}
