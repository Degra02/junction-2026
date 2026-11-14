import { useCallback, useEffect, useState } from "react";
import { ApiClientError, analysisEventsUrl, getAnalysis } from "../lib/api";
import type { Analysis, AnalysisEvent, Step } from "../lib/contracts";

export interface AnalysisStreamState {
  readonly analysis: Analysis | null;
  readonly loading: boolean;
  readonly isStreaming: boolean;
  readonly error: string | null;
  readonly notFound: boolean;
  readonly reconnect: () => void;
}

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

export function useAnalysisStream(id: string | undefined, replay: boolean): AnalysisStreamState {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState<boolean>(false);
  const [attempt, setAttempt] = useState<number>(0);

  const reconnect = useCallback(() => {
    setAttempt((n) => n + 1);
  }, []);

  useEffect(() => {
    if (!id) {
      setLoading(false);
      setNotFound(true);
      return;
    }

    let cancelled = false;
    let settled = false;
    const abortController = new AbortController();

    setLoading(true);
    setError(null);
    setNotFound(false);
    if (replay) {
      setAnalysis(null);
    }

    const es = new EventSource(analysisEventsUrl(id, replay));
    setIsStreaming(true);

    const onSnapshot = (ev: MessageEvent<string>) => {
      if (cancelled) return;
      try {
        const parsed = JSON.parse(ev.data) as Extract<AnalysisEvent, { type: "snapshot" }>;
        setAnalysis(parsed.analysis);
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
        setAnalysis((prev) =>
          prev
            ? {
                ...prev,
                status: "running",
                queue_position: null,
                steps: mergeStep(prev.steps, parsed.step),
              }
            : prev,
        );
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
        // Probe GET /api/analyses/{id} to surface 404 or load the stored record cleanly.
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
