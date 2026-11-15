//! Runs the stages of one analysis against the worker, persisting and broadcasting each step.

use std::{
    collections::{HashMap, VecDeque},
    convert::Infallible,
    sync::{Arc, Mutex, PoisonError},
    time::Duration,
};

use chrono::{DateTime, Utc};
use futures_util::future::join_all;
use junction_contracts::{
    Analysis, AnalysisEvent, AnalysisStatus, StageName, StagePatch, Step, StepState,
};
use tokio::{
    sync::Semaphore,
    time::{Instant, MissedTickBehavior},
};
use tokio_util::task::TaskTracker;
use uuid::Uuid;

use crate::{
    config::Config,
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
    &[StageName::Explain, StageName::Graph],
];

/// How often the worker is asked for the progress notes of the running stages.
const PROGRESS_POLL: Duration = Duration::from_secs(1);

#[derive(Clone)]
pub struct Pipeline {
    db: Db,
    worker: WorkerClient,
    hub: Hub,
    /// Analyses running at once.
    slots: Arc<Semaphore>,
    /// Model stages running at once, across analyses: CPU inference is the bottleneck, while
    /// the I/O stages (LLM calls, retrieval) of different analyses overlap freely.
    inference: Arc<Semaphore>,
    /// Analyses waiting for a slot, oldest first.
    queue: Arc<Mutex<VecDeque<Uuid>>>,
    limits: Arc<Limits>,
    tasks: TaskTracker,
}

struct Limits {
    stage_timeout: Duration,
    analysis_timeout: Duration,
    disabled: Vec<StageName>,
}

impl Pipeline {
    pub fn new(db: Db, worker: WorkerClient, hub: Hub, config: &Config) -> Self {
        Self {
            db,
            worker,
            hub,
            slots: Arc::new(Semaphore::new(config.max_concurrent_analyses.max(1))),
            inference: Arc::new(Semaphore::new(config.max_concurrent_inference.max(1))),
            queue: Arc::default(),
            limits: Arc::new(Limits {
                stage_timeout: config.stage_timeout,
                analysis_timeout: config.analysis_timeout,
                disabled: config.stages_disabled.clone(),
            }),
            tasks: TaskTracker::new(),
        }
    }

    /// Starts a persisted, queued analysis in the background. Steps that are not pending (kept
    /// from the analysis this one re-runs) are left as they are.
    pub fn spawn(&self, analysis: Analysis) {
        self.hub.open(analysis.id);
        self.queue().push_back(analysis.id);
        let this = self.clone();
        self.tasks.spawn(async move { this.run(analysis).await });
    }

    /// Background tasks, for tests and shutdown.
    pub const fn tasks(&self) -> &TaskTracker {
        &self.tasks
    }

    /// Place of a waiting analysis in the queue (1 = next to start); `None` once it started.
    pub fn queue_position(&self, id: Uuid) -> Option<u32> {
        let place = self.queue().iter().position(|queued| *queued == id)?;
        u32::try_from(place + 1).ok()
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
        let id = a.id;
        let slot = self.slots.acquire().await;
        self.leave_queue(id);
        let Ok(_slot) = slot else {
            return;
        };
        let deadline = Instant::now() + self.limits.analysis_timeout;
        a.status = AnalysisStatus::Running;
        self.persist(&a).await;

        for group in SCHEDULE {
            let mut runnable = Vec::with_capacity(group.len());
            let mut changed = false;
            for &stage in *group {
                if a.step(stage).state != StepState::Pending {
                    continue;
                }
                changed = true;
                if let Some(reason) = self.skip_reason(stage, &a, deadline) {
                    self.set_step(&mut a, stage, StepState::Skipped, None, Some(reason));
                } else {
                    self.set_step(&mut a, stage, StepState::Running, None, None);
                    runnable.push(stage);
                }
            }
            if changed {
                self.persist(&a).await;
            }
            if runnable.is_empty() {
                continue;
            }

            let snapshot = &a;
            let calls = join_all(
                runnable
                    .iter()
                    .map(|&stage| self.call(stage, snapshot, deadline)),
            );
            let outcomes = tokio::select! {
                outcomes = calls => outcomes,
                never = self.relay_progress(snapshot) => match never {},
            };

            for (stage, outcome, elapsed) in outcomes {
                let ms = u64::try_from(elapsed.as_millis()).unwrap_or(u64::MAX);
                // Before set_step, so the broadcast step carries its duration.
                a.step_mut(stage).duration_ms = Some(ms);
                self.apply_outcome(&mut a, stage, outcome).await;
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

    async fn apply_outcome(&self, a: &mut Analysis, stage: StageName, outcome: StageOutcome) {
        let id = a.id;
        match outcome {
            StageOutcome::Patch(patch) => {
                let graph_patch = match &patch {
                    StagePatch::Graph(gp) => Some(gp.clone()),
                    _ => None,
                };
                match a.apply(patch) {
                    Ok(report) => {
                        if let Some(gp) = graph_patch
                            && let Err(err) = self.db.ingest_graph(a, &gp).await
                        {
                            tracing::error!(%id, error = %err, "failed to persist graph patch");
                            self.set_step(
                                a,
                                stage,
                                Self::failed_state(),
                                None,
                                Some("could not store graph observations".into()),
                            );
                        } else {
                            self.set_step(a, stage, StepState::Done, report.summary(), None);
                        }
                    }
                    Err(e) => {
                        let error = format!("rejected by the contract: {e}");
                        self.set_step(a, stage, Self::failed_state(), None, Some(error));
                    }
                }
            }
            StageOutcome::NotImplemented => {
                let error = "not implemented yet".to_owned();
                self.set_step(a, stage, StepState::Skipped, None, Some(error));
            }
            StageOutcome::Failed(error) => {
                tracing::warn!(%id, %stage, %error, "stage failed");
                self.set_step(a, stage, Self::failed_state(), None, Some(error));
            }
        }
    }

    const fn failed_state() -> StepState {
        StepState::Failed
    }

    /// Calls the worker for one stage; the time a model stage waits for its turn is not part
    /// of the returned duration.
    async fn call(
        &self,
        stage: StageName,
        a: &Analysis,
        deadline: Instant,
    ) -> (StageName, StageOutcome, Duration) {
        let _turn = if is_model_stage(stage) {
            self.inference.acquire().await.ok()
        } else {
            None
        };
        let started = Instant::now();
        // Whole milliseconds, so a timeout capped by the budget reads "timed out after 1.5s".
        let left = deadline.saturating_duration_since(started).as_millis();
        let left = Duration::from_millis(u64::try_from(left).unwrap_or(u64::MAX));
        let outcome = if left.is_zero() {
            StageOutcome::Failed("the analysis ran out of time".into())
        } else {
            let timeout = self.limits.stage_timeout.min(left);
            self.worker.run_stage(stage, a, timeout).await
        };
        (stage, outcome, started.elapsed())
    }

    /// Forwards the progress notes of the running stages ("14 sources so far") as step events.
    /// They are live-only: the step's final `detail` comes from its patch.
    async fn relay_progress(&self, a: &Analysis) -> Infallible {
        let mut tick = tokio::time::interval_at(Instant::now() + PROGRESS_POLL, PROGRESS_POLL);
        tick.set_missed_tick_behavior(MissedTickBehavior::Delay);
        let mut shown: HashMap<StageName, String> = HashMap::new();
        loop {
            tick.tick().await;
            for (stage, note) in self.worker.progress(a.id).await {
                let step = a.step(stage);
                if step.state == StepState::Running && shown.get(&stage) != Some(&note) {
                    let step = Step {
                        detail: Some(note.clone()),
                        ..step.clone()
                    };
                    self.hub.send(a.id, AnalysisEvent::Step { step });
                    shown.insert(stage, note);
                }
            }
        }
    }

    /// Why `stage` cannot run on the current record, if it cannot.
    fn skip_reason(&self, stage: StageName, a: &Analysis, deadline: Instant) -> Option<String> {
        if self.limits.disabled.contains(&stage) {
            return Some("switched off by the operator".into());
        }
        match stage {
            StageName::Extract => None,
            _ if a.document.is_none() => Some("needs the extracted document".into()),
            _ if Instant::now() >= deadline => Some("the analysis ran out of time".into()),
            StageName::Explain if a.scores.is_none() => Some("needs the scores".into()),
            _ => None,
        }
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

    /// Removes `id` from the queue and tells the analyses behind it their new place.
    fn leave_queue(&self, id: Uuid) {
        let mut queue = self.queue();
        queue.retain(|queued| *queued != id);
        for (place, waiting) in queue.iter().enumerate() {
            if let Ok(position) = u32::try_from(place + 1) {
                self.hub.send(*waiting, AnalysisEvent::Queue { position });
            }
        }
    }

    fn queue(&self) -> std::sync::MutexGuard<'_, VecDeque<Uuid>> {
        self.queue.lock().unwrap_or_else(PoisonError::into_inner)
    }
}

/// A copy of the finished analysis `source` that runs again from `from`: the output of the
/// earlier stages is kept, `from` and every stage scheduled with or after it start over.
pub fn rerun_record(
    source: Analysis,
    from: StageName,
    id: Uuid,
    pipeline_version: String,
    now: DateTime<Utc>,
) -> Analysis {
    let mut a = Analysis {
        id,
        schema_version: junction_contracts::SCHEMA_VERSION,
        pipeline_version,
        created_at: now,
        updated_at: now,
        status: AnalysisStatus::Queued,
        queue_position: None,
        error: None,
        ..source
    };
    let first = SCHEDULE
        .iter()
        .position(|group| group.contains(&from))
        .expect("every stage is scheduled");
    for &stage in SCHEDULE[first..].iter().copied().flatten() {
        a.clear_output(stage);
        *a.step_mut(stage) = Step::pending(stage);
    }
    a
}

/// Stages that run models on the CPU.
const fn is_model_stage(stage: StageName) -> bool {
    matches!(
        stage,
        StageName::Story
            | StageName::SignalsSingle
            | StageName::SignalsCoordinated
            | StageName::Graph
    )
}

/// `done` needs a document and scores; otherwise `failed` with the reason of the stage that
/// produced nothing.
fn final_status(a: &Analysis) -> (AnalysisStatus, Option<String>) {
    let why = |stage: StageName, what: &str| {
        let cause = a.step(stage).error.as_deref().unwrap_or("no output");
        Some(format!("{what} ({stage}): {cause}"))
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
