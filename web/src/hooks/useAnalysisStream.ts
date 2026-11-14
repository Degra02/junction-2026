import { useCallback, useEffect, useRef, useState } from "react";
import { ApiClientError, analysisEventsUrl, getAnalysis } from "../lib/api";
import type { Analysis, AnalysisEvent, Family, StageName, Step, StepState } from "../lib/contracts";

/** What the client saw of one stage while it ran: its live notes and when it started/ended. */
export interface StageActivity {
  /** Distinct progress notes in arrival order (live runs only; replays have none). */
  readonly notes: readonly string[];
  /** Client clock (ms) when the stage was first seen running. */
  readonly startedAt: number | null;
  /** Client clock (ms) when the stage was first seen finished. */
  readonly finishedAt: number | null;
}

export type ActivityLog = Partial<Record<StageName, StageActivity>>;

export interface AnalysisStreamState {
  readonly analysis: Analysis | null;
  readonly activity: ActivityLog;
  readonly loading: boolean;
  readonly isStreaming: boolean;
  readonly error: string | null;
  readonly notFound: boolean;
  readonly reconnect: () => void;
}

const SINGLE_FAMILIES: Partial<Record<Family, true>> = {
  techniques: true,
  rhetoric: true,
  tone: true,
  claim_support: true,
  fact_checks: true,
  source_profile: true,
};

function mergeStep(steps: readonly Step[], incoming: Step): Step[] {
  let matched = false;
  const updated = steps.map((s) => {
    if (s.name === incoming.name) {
      matched = true;
      return incoming;
    }
    return s;
  });
  return matched ? updated : [...updated, incoming];
}

function isStageDone(steps: readonly Step[], stage: StageName): boolean {
  const st = steps.find((s) => s.name === stage)?.state;
  return st === "done" || st === "skipped";
}

/** Records a step event in the activity log; returns the same object when nothing changed. */
function recordStep(log: ActivityLog, step: Step, now: number): ActivityLog {
  const prev = log[step.name] ?? { notes: [], startedAt: null, finishedAt: null };
  let next = prev;
  if (step.state === "running") {
    const note = step.detail?.trim();
    const last = prev.notes[prev.notes.length - 1];
    let notes = prev.notes;
    if (note && note !== last) {
      // "Reading related reports: 2 of 8" → "5 of 8" updates the line instead of adding one.
      const sameLine = last !== undefined && last.replace(/\d+/g, "#") === note.replace(/\d+/g, "#");
      notes = sameLine ? [...prev.notes.slice(0, -1), note] : [...prev.notes, note];
    }
    if (prev.startedAt === null || notes !== prev.notes) {
      next = { ...prev, notes, startedAt: prev.startedAt ?? now };
    }
  } else if (step.state !== "pending" && prev.finishedAt === null) {
    next = { ...prev, startedAt: prev.startedAt ?? now, finishedAt: now };
  }
  return next === prev ? log : { ...log, [step.name]: next };
}

/**
 * In `?replay=true` mode, the SSE stream starts from an empty `Snapshot` and replays each
 * `Step` before sending the full `Analysis` in `Done`. The stored `Analysis` is fetched once
 * and its fields are revealed as the replayed steps finish, so a replay shows the same
 * intermediate results (document, queries, sources, story) as the live run did.
 */
function projectReplayProgress(current: Analysis, fullRecord: Analysis | null): Analysis {
  if (!fullRecord || current.status === "done" || current.status === "failed") {
    return current;
  }

  const steps = current.steps;
  const extractDone = isStageDone(steps, "extract");
  const understandDone = isStageDone(steps, "understand");
  const retrieveDone = isStageDone(steps, "retrieve");
  const storyDone = isStageDone(steps, "story");
  const singleDone = isStageDone(steps, "signals_single");
  const coordDone = isStageDone(steps, "signals_coordinated");
  const scoreDone = isStageDone(steps, "score");
  const explainDone = isStageDone(steps, "explain");

  const context = !retrieveDone
    ? []
    : storyDone
      ? fullRecord.context
      : fullRecord.context.map((c) => ({ ...c, similarity: null, in_story: null, story_reason: null }));

  const evidence = fullRecord.evidence.filter((ev) =>
    SINGLE_FAMILIES[ev.family] ? singleDone : coordDone,
  );

  return {
    ...current,
    language: extractDone ? fullRecord.language : null,
    document: extractDone ? fullRecord.document : null,
    topic: understandDone ? fullRecord.topic : null,
    claims: understandDone ? fullRecord.claims : [],
    queries: understandDone ? fullRecord.queries : [],
    context,
    sources: retrieveDone ? fullRecord.sources : [],
    evidence,
    scores: scoreDone ? fullRecord.scores : null,
    explanation: explainDone ? fullRecord.explanation : null,
  };
}

export function useAnalysisStream(id: string | undefined, replay: boolean): AnalysisStreamState {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [activity, setActivity] = useState<ActivityLog>({});
  const [loading, setLoading] = useState(true);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const replayFullRef = useRef<Analysis | null>(null);

  const reconnect = useCallback(() => {
    setAttempt((n) => n + 1);
  }, []);

  useEffect(() => {
    if (!id) {
      setAnalysis(null);
      setLoading(false);
      setIsStreaming(false);
      return;
    }

    let cancelled = false;
    let settled = false;
    const abortController = new AbortController();
    const lastState = new Map<StageName, StepState>();
    replayFullRef.current = null;

    setLoading(true);
    setError(null);
    setNotFound(false);
    setActivity({});
    if (replay) {
      setAnalysis(null);
      getAnalysis(id, abortController.signal)
        .then((full) => {
          if (cancelled) return;
          replayFullRef.current = full;
          setAnalysis((prev) => (prev ? projectReplayProgress(prev, full) : prev));
        })
        .catch(() => {
          // A missing record surfaces through the SSE error path.
        });
    }

    // The API saves a stage's output just after announcing it done, and before the next stage
    // starts: fetching on every state change picks it up by the next transition at the latest.
    // The SSE steps stay authoritative; the fetched record only adds the stage outputs.
    const hydrate = () => {
      if (replay || cancelled || settled) return;
      getAnalysis(id, abortController.signal)
        .then((fresh) => {
          if (cancelled || settled) return;
          setAnalysis((prev) => {
            if (!prev) return fresh;
            if (prev.status === "done" || prev.status === "failed") return prev;
            return { ...fresh, status: prev.status, queue_position: prev.queue_position, steps: prev.steps };
          });
        })
        .catch(() => {
          // Non-fatal: the `done` event carries the full record.
        });
    };

    const es = new EventSource(analysisEventsUrl(id, replay));
    setIsStreaming(true);

    const onSnapshot = (ev: MessageEvent<string>) => {
      if (cancelled) return;
      try {
        const parsed = JSON.parse(ev.data) as Extract<AnalysisEvent, { type: "snapshot" }>;
        const now = Date.now();
        for (const step of parsed.analysis.steps) lastState.set(step.name, step.state);
        setActivity((log) =>
          parsed.analysis.steps.reduce((acc, step) => recordStep(acc, step, now), log),
        );
        setAnalysis(
          replay ? projectReplayProgress(parsed.analysis, replayFullRef.current) : parsed.analysis,
        );
        setLoading(false);
        setError(null);
      } catch {
        // Ignore a malformed frame.
      }
    };

    const onQueue = (ev: MessageEvent<string>) => {
      if (cancelled) return;
      try {
        const parsed = JSON.parse(ev.data) as Extract<AnalysisEvent, { type: "queue" }>;
        setAnalysis((prev) =>
          prev ? { ...prev, status: "queued", queue_position: parsed.position } : prev,
        );
      } catch {
        // Ignore a malformed frame.
      }
    };

    const onStep = (ev: MessageEvent<string>) => {
      if (cancelled) return;
      try {
        const { step } = JSON.parse(ev.data) as Extract<AnalysisEvent, { type: "step" }>;
        const changedState = lastState.get(step.name) !== step.state;
        lastState.set(step.name, step.state);
        const now = Date.now();
        setActivity((log) => recordStep(log, step, now));
        setAnalysis((prev) => {
          if (!prev) return prev;
          const next: Analysis = {
            ...prev,
            status: "running",
            queue_position: null,
            steps: mergeStep(prev.steps, step),
          };
          return replay ? projectReplayProgress(next, replayFullRef.current) : next;
        });
        if (changedState) hydrate();
      } catch {
        // Ignore a malformed frame.
      }
    };

    const onDone = (ev: MessageEvent<string>) => {
      if (cancelled) return;
      settled = true;
      try {
        const parsed = JSON.parse(ev.data) as Extract<AnalysisEvent, { type: "done" }>;
        const now = Date.now();
        setActivity((log) =>
          parsed.analysis.steps.reduce((acc, step) => recordStep(acc, step, now), log),
        );
        setAnalysis(parsed.analysis);
        setLoading(false);
        setError(null);
      } catch {
        // Ignore a malformed frame.
      }
      setIsStreaming(false);
      es.close();
    };

    es.addEventListener("snapshot", onSnapshot as EventListener);
    es.addEventListener("queue", onQueue as EventListener);
    es.addEventListener("step", onStep as EventListener);
    es.addEventListener("done", onDone as EventListener);

    es.onerror = () => {
      if (cancelled || settled) return;
      if (es.readyState === EventSource.CLOSED) {
        setIsStreaming(false);
        getAnalysis(id, abortController.signal)
          .then((record) => {
            if (cancelled) return;
            setAnalysis(record);
            setLoading(false);
            if (record.status === "done" || record.status === "failed") {
              settled = true;
            } else {
              setError("Lost the live connection. Reconnect to resume.");
            }
          })
          .catch((err: unknown) => {
            if (cancelled) return;
            setLoading(false);
            if (err instanceof ApiClientError && err.status === 404) {
              setNotFound(true);
            } else {
              setError(err instanceof Error ? err.message : "Could not load the analysis.");
            }
          });
      }
    };

    return () => {
      cancelled = true;
      abortController.abort();
      es.close();
    };
  }, [id, replay, attempt]);

  return { analysis, activity, loading, isStreaming, error, notFound, reconnect };
}
