import type {
  Analysis,
  Created,
  ErrorBody,
  Health,
  Input,
  GraphPayload,
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

/**
 * What went wrong and what to do next, in plain words, for any error a request can throw.
 * Server messages are lower-case fragments ("the text is empty"); this makes them sentences
 * and adds the way out.
 */
export function describeError(err: unknown): string {
  if (!(err instanceof ApiClientError)) {
    return "Can't reach the service. Check your connection and try again.";
  }
  switch (err.code) {
    case "rate_limited":
      return "Too many new analyses from your connection. Wait a minute and try again; the examples still work.";
    case "busy":
      return "The service reached its hourly limit of new analyses. Earlier results and the examples still work.";
    case "not_found":
      return "This analysis no longer exists. Start a new one.";
  }
  if (err.status === 502 || err.status === 503) {
    return "The service is restarting. Try again in a moment.";
  }
  if (err.code === "invalid_input" && /url/i.test(err.message)) {
    const reason = /^not a valid url/i.test(err.message) ? "That link is not valid" : capitalize(err.message);
    return `${reason}. Check the link, or paste the article text instead.`;
  }
  return `${capitalize(err.message)}.`;
}

function capitalize(text: string): string {
  const t = text.trim().replace(/\.$/, "");
  return t.charAt(0).toUpperCase() + t.slice(1);
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

/** The source graph; null while no graph is published (404). */
export async function getGraph(signal?: AbortSignal): Promise<GraphPayload | null> {
  const res = await fetch("/api/graph", {
    headers: { Accept: "application/json" },
    signal,
  });
  if (res.status === 404) {
    return null;
  }
  if (!res.ok) {
    throw await parseError(res);
  }
  return (await res.json()) as GraphPayload;
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
