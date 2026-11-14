import { useCallback, useEffect, useRef, useState } from "react";
import { ApiClientError, analysisEventsUrl, getAnalysis } from "../lib/api";
import type { Analysis, AnalysisEvent, Family, StageName, Step } from "../lib/contracts";

export interface AnalysisStreamState {
  readonly analysis: Analysis | null;
  readonly loading: boolean;
  readonly isStreaming: boolean;
  readonly error: string | null;
  readonly notFound: boolean;
  readonly reconnect: () => void;
}

const SINGLE_FAMILIES: Partial<Record<Family, true>> = {
  techniques: true,
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

/**
 * In `?replay=true` mode, the SSE stream starts from an empty `Snapshot` and replays each
 * `Step` before sending the full `Analysis` in `Done`. By pre-fetching the stored `Analysis`
 * once in parallel and gating its fields by which replayed steps have finished, the UI shows
 * real extracted text, search queries, visited websites, and story clusters live during replay.
 */
function projectReplayProgress(
  current: Analysis,
  fullRecord: Analysis | null,
): Analysis {
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
      : fullRecord.context.map((c) => ({
          ...c,
          similarity: null,
          in_story: null,
          story_reason: null,
        }));

  const evidence = fullRecord.evidence.filter((ev) => {
    if (SINGLE_FAMILIES[ev.family]) return singleDone;
    return coordDone;
  });

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
  const [loading, setLoading] = useState<boolean>(true);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState<boolean>(false);
  const [attempt, setAttempt] = useState<number>(0);
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
    replayFullRef.current = null;

    setLoading(true);
    setError(null);
    setNotFound(false);
    if (replay) {
      setAnalysis(null);
      // Preload stored record so replay steps reveal real intermediate outputs stage-by-stage
      getAnalysis(id, abortController.signal)
        .then((full) => {
          if (cancelled) return;
          replayFullRef.current = full;
          setAnalysis((prev) => (prev ? projectReplayProgress(prev, full) : prev));
        })
        .catch(() => {
          // Handled by SSE error path if 404
        });
    }

    const hydrateIntermediateData = () => {
      if (replay || cancelled || settled) return;
      getAnalysis(id, abortController.signal)
        .then((fresh) => {
          if (cancelled || settled) return;
          setAnalysis((prev) => {
            if (!prev || prev.status === "done" || prev.status === "failed") {
              return fresh;
            }
            // Keep latest live SSE steps while hydrating newly persisted stage data
            const mergedSteps = fresh.steps.reduce<Step[]>(
              (acc, s) => mergeStep(acc, s),
              [...prev.steps],
            );
            return {
              ...fresh,
              status: fresh.status === "done" || fresh.status === "failed" ? fresh.status : prev.status,
              steps: mergedSteps,
            };
          });
        })
        .catch(() => {
          // Non-fatal; final `done` event delivers complete record
        });
    };

    const es = new EventSource(analysisEventsUrl(id, replay));
    setIsStreaming(true);

    const onSnapshot = (ev: MessageEvent<string>) => {
      if (cancelled) return;
      try {
        const parsed = JSON.parse(ev.data) as Extract<AnalysisEvent, { type: "snapshot" }>;
        setAnalysis(
          replay
            ? projectReplayProgress(parsed.analysis, replayFullRef.current)
            : parsed.analysis,
        );
        setLoading(false);
        setError(null);
      } catch {
        // Ignore malformed frame
      }
    };

    const onQueue = (ev: MessageEvent<string>) => {
      if (cancelled) return;
      try {
        const parsed = JSON.parse(ev.data) as Extract<AnalysisEvent, { type: "queue" }>;
        setAnalysis((prev) =>
          prev
            ? {
                ...prev,
                status: "queued",
                queue_position: parsed.position,
              }
            : prev,
        );
      } catch {
        // Ignore malformed frame
      }
    };

    const onStep = (ev: MessageEvent<string>) => {
      if (cancelled) return;
      try {
        const parsed = JSON.parse(ev.data) as Extract<AnalysisEvent, { type: "step" }>;
        setAnalysis((prev) => {
          if (!prev) return prev;
          const next: Analysis = {
            ...prev,
            status: "running",
            queue_position: null,
            steps: mergeStep(prev.steps, parsed.step),
          };
          return replay ? projectReplayProgress(next, replayFullRef.current) : next;
        });

        // Whenever a live stage finishes, pull its persisted data (`document`, `queries`, `context`, etc.)
        if (!replay && parsed.step.state === "done") {
          hydrateIntermediateData();
        }
      } catch {
        // Ignore malformed frame
      }
    };

    const onDone = (ev: MessageEvent<string>) => {
      if (cancelled) return;
      settled = true;
      try {
        const parsed = JSON.parse(ev.data) as Extract<AnalysisEvent, { type: "done" }>;
        setAnalysis(parsed.analysis);
        setLoading(false);
        setError(null);
      } catch {
        // Ignore malformed frame
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
              setError("Live progress stream disconnected. Reconnect to resume updates.");
            }
          })
          .catch((err: unknown) => {
            if (cancelled) return;
            setLoading(false);
            if (err instanceof ApiClientError && err.status === 404) {
              setNotFound(true);
            } else if (err instanceof Error) {
              setError(err.message);
            } else {
              setError("Could not load analysis.");
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

  return { analysis, loading, isStreaming, error, notFound, reconnect };
}
