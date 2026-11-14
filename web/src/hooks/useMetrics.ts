import { useCallback, useEffect, useState } from "react";
import { getMetrics, getStats } from "../lib/api";
import type { MetricsPayload, Stats } from "../lib/contracts";

export interface MetricsState {
  readonly metrics: MetricsPayload | null;
  readonly stats: Stats | null;
  readonly notPublishedYet: boolean;
  readonly loading: boolean;
  readonly error: string | null;
  readonly refresh: () => void;
}

export function useMetrics(): MetricsState {
  const [metrics, setMetrics] = useState<MetricsPayload | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [notPublishedYet, setNotPublishedYet] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState<number>(0);

  const refresh = useCallback(() => {
    setTick((n) => n + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.allSettled([getMetrics(controller.signal), getStats(controller.signal)]).then(
      ([metricsRes, statsRes]) => {
        if (cancelled) return;
        if (metricsRes.status === "fulfilled") {
          setMetrics(metricsRes.value);
          setNotPublishedYet(metricsRes.value === null);
        } else {
          const reason = metricsRes.reason;
          if (reason instanceof Error && reason.name === "AbortError") return;
          setError(reason instanceof Error ? reason.message : "Failed to load evaluation metrics.");
        }

        if (statsRes.status === "fulfilled") {
          setStats(statsRes.value);
        }
        setLoading(false);
      },
    );

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [tick]);

  return { metrics, stats, notPublishedYet, loading, error, refresh };
}
