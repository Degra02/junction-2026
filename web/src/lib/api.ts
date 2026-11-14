import type {
  Analysis,
  Created,
  ErrorBody,
  Health,
  Input,
  MetricsPayload,
  StageName,
  Stats,
} from "./contracts";

export class ApiClientError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
  }
}

async function parseError(res: Response): Promise<ApiClientError> {
  try {
    const body = (await res.json()) as Partial<ErrorBody>;
    if (body && typeof body.message === "string") {
      return new ApiClientError(res.status, body.error ?? "http_error", body.message);
    }
  } catch {
    // Non-JSON upstream error (e.g. proxy 502 while worker restarts)
  }
  return new ApiClientError(
    res.status,
    `http_${res.status}`,
    res.status === 502 || res.status === 503
      ? "The analysis service is restarting or temporarily unreachable."
      : `Request failed with status ${res.status}.`,
  );
}

export async function createAnalysis(
  input: Input,
  options?: { readonly force?: boolean },
): Promise<Created> {
  const query = options?.force ? "?force=true" : "";
  const res = await fetch(`/api/analyses${query}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    throw await parseError(res);
  }
  return (await res.json()) as Created;
}

export async function getAnalysis(id: string, signal?: AbortSignal): Promise<Analysis> {
  const res = await fetch(`/api/analyses/${encodeURIComponent(id)}`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!res.ok) {
    throw await parseError(res);
  }
  return (await res.json()) as Analysis;
}

export async function rerunAnalysis(id: string, from: StageName): Promise<Created> {
  const params = new URLSearchParams({ from });
  const res = await fetch(`/api/analyses/${encodeURIComponent(id)}/rerun?${params.toString()}`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw await parseError(res);
  }
  return (await res.json()) as Created;
}

export async function getMetrics(signal?: AbortSignal): Promise<MetricsPayload | null> {
  const res = await fetch("/api/metrics", {
    headers: { Accept: "application/json" },
    signal,
  });
  if (res.status === 404) {
    return null;
  }
  if (!res.ok) {
    throw await parseError(res);
  }
  return (await res.json()) as MetricsPayload;
}

export async function getStats(signal?: AbortSignal): Promise<Stats> {
  const res = await fetch("/api/stats", {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!res.ok) {
    throw await parseError(res);
  }
  return (await res.json()) as Stats;
}

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  const res = await fetch("/api/health", {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!res.ok) {
    throw await parseError(res);
  }
  return (await res.json()) as Health;
}

export function analysisEventsUrl(id: string, replay: boolean): string {
  const base = `/api/analyses/${encodeURIComponent(id)}/events`;
  return replay ? `${base}?replay=true` : base;
}
