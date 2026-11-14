//! Runs the stages of one analysis against the worker, persisting and broadcasting each step.

use std::{sync::Arc, time::Instant};

use chrono::Utc;
use futures_util::future::join_all;
use junction_contracts::{Analysis, AnalysisEvent, AnalysisStatus, StageName, StepState};
use tokio::sync::Semaphore;
use tokio_util::task::TaskTracker;

use crate::{
    db::Db,
    events::Hub,
    worker::{StageOutcome, WorkerClient},
};

/// Stages in execution order; stages in one group run in parallel on the same snapshot.
const SCHEDULE: &[&[StageName]] = &[
    &[StageName::Extract],
    &[StageName::Understand],
    &[StageName::Retrieve],
    &[StageName::Story],
    &[StageName::SignalsSingle, StageName::SignalsCoordinated],
    &[StageName::Score],
    &[StageName::Explain],
];

#[derive(Clone)]
pub struct Pipeline {
    db: Db,
    worker: WorkerClient,
    hub: Hub,
    permits: Arc<Semaphore>,
    tasks: TaskTracker,
}

impl Pipeline {
    pub fn new(db: Db, worker: WorkerClient, hub: Hub, max_concurrent: usize) -> Self {
        Self {
            db,
            worker,
            hub,
            permits: Arc::new(Semaphore::new(max_concurrent.max(1))),
            tasks: TaskTracker::new(),
        }
    }

    /// Starts a persisted, queued analysis in the background.
    pub fn spawn(&self, analysis: Analysis) {
        self.hub.open(analysis.id);
        let this = self.clone();
        self.tasks.spawn(async move { this.run(analysis).await });
    }

    /// Background tasks, for tests and shutdown.
    pub const fn tasks(&self) -> &TaskTracker {
        &self.tasks
    }

    /// Marks analyses interrupted by a restart as failed, so clients stop waiting and a new
    /// submission of the same input runs again.
    pub async fn recover(&self) -> anyhow::Result<usize> {
        let unfinished = self.db.unfinished().await?;
        let count = unfinished.len();
        for mut analysis in unfinished {
            for step in &mut analysis.steps {
                if matches!(step.state, StepState::Pending | StepState::Running) {
                    step.state = StepState::Skipped;
                    step.error = Some("interrupted by a server restart".into());
                }
            }
            analysis.status = AnalysisStatus::Failed;
            analysis.error = Some("interrupted by a server restart; submit it again".into());
            analysis.updated_at = Utc::now();
            self.db.save(&analysis).await?;
        }
        Ok(count)
    }

    async fn run(&self, mut a: Analysis) {
        let Ok(_permit) = self.permits.clone().acquire_owned().await else {
            return;
        };
        let id = a.id;
        a.status = AnalysisStatus::Running;
        self.persist(&a).await;

        for group in SCHEDULE {
            let mut runnable = Vec::with_capacity(group.len());
            for &stage in *group {
                if let Some(reason) = skip_reason(stage, &a) {
                    self.set_step(&mut a, stage, StepState::Skipped, None, Some(reason));
                } else {
                    self.set_step(&mut a, stage, StepState::Running, None, None);
                    runnable.push(stage);
                }
            }
            self.persist(&a).await;
            if runnable.is_empty() {
                continue;
            }

            let snapshot = &a;
            let started = Instant::now();
            let outcomes = join_all(runnable.iter().map(|&stage| async move {
                let outcome = self.worker.run_stage(stage, snapshot).await;
                (stage, outcome, started.elapsed())
            }))
            .await;

            for (stage, outcome, elapsed) in outcomes {
                let ms = u64::try_from(elapsed.as_millis()).unwrap_or(u64::MAX);
                // Before set_step, so the broadcast step carries its duration.
                a.step_mut(stage).duration_ms = Some(ms);
                match outcome {
                    StageOutcome::Patch(patch) => match a.apply(patch) {
                        Ok(report) => {
                            self.set_step(&mut a, stage, StepState::Done, report.summary(), None);
                        }
                        Err(e) => {
                            let error = format!("rejected by the contract: {e}");
                            self.set_step(&mut a, stage, StepState::Failed, None, Some(error));
                        }
                    },
                    StageOutcome::NotImplemented => {
                        let error = "not implemented yet".to_owned();
                        self.set_step(&mut a, stage, StepState::Skipped, None, Some(error));
                    }
                    StageOutcome::Failed(error) => {
                        tracing::warn!(%id, %stage, %error, "stage failed");
                        self.set_step(&mut a, stage, StepState::Failed, None, Some(error));
                    }
                }
            }
            self.persist(&a).await;
        }

        (a.status, a.error) = final_status(&a);
        a.updated_at = Utc::now();
        self.persist(&a).await;
        self.hub.finish(
            id,
            AnalysisEvent::Done {
                analysis: Box::new(a),
            },
        );
    }

    fn set_step(
        &self,
        a: &mut Analysis,
        name: StageName,
        state: StepState,
        detail: Option<String>,
        error: Option<String>,
    ) {
        let step = a.step_mut(name);
        step.state = state;
        step.detail = detail;
        step.error = error;
        let step = step.clone();
        a.updated_at = Utc::now();
        self.hub.send(a.id, AnalysisEvent::Step { step });
    }

    async fn persist(&self, a: &Analysis) {
        if let Err(e) = self.db.save(a).await {
            tracing::error!(id = %a.id, error = ?e, "saving analysis failed");
        }
    }
}

/// Why `stage` cannot run on the current record, if it cannot.
fn skip_reason(stage: StageName, a: &Analysis) -> Option<String> {
    match stage {
        StageName::Extract => None,
        _ if a.document.is_none() => Some("needs the extracted document".into()),
        StageName::Explain if a.scores.is_none() => Some("needs the scores".into()),
        _ => None,
    }
}

/// `done` needs a document and scores; otherwise `failed` with the reason of the stage that
/// produced nothing.
fn final_status(a: &Analysis) -> (AnalysisStatus, Option<String>) {
    let why = |stage: StageName, what: &str| {
        let step = a.steps.iter().find(|s| s.name == stage);
        let cause = step
            .and_then(|s| s.error.clone())
            .unwrap_or_else(|| "no output".into());
        Some(format!("{what}: {stage} {cause}"))
    };
    if a.document.is_none() {
        (
            AnalysisStatus::Failed,
            why(StageName::Extract, "could not read the input"),
        )
    } else if a.scores.is_none() {
        (
            AnalysisStatus::Failed,
            why(StageName::Score, "no score was produced"),
        )
    } else {
        (AnalysisStatus::Done, None)
    }
}
