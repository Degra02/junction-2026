/** The analyses this browser opened, newest first, so they can be found again without the link. */

const KEY = "junction-recent";
const MAX = 6;

export interface RecentAnalysis {
  readonly id: string;
  readonly title: string;
  /** Outlet domain, or null for pasted text. */
  readonly domain: string | null;
  /** When the analysis was created (ISO). */
  readonly at: string;
}

export function loadRecent(): RecentAnalysis[] {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(parsed) ? (parsed as RecentAnalysis[]).slice(0, MAX) : [];
  } catch {
    return [];
  }
}

export function rememberAnalysis(entry: RecentAnalysis): void {
  try {
    const rest = loadRecent().filter((r) => r.id !== entry.id);
    window.localStorage.setItem(KEY, JSON.stringify([entry, ...rest].slice(0, MAX)));
  } catch {
    // Storage can be full or disabled; the list is a convenience.
  }
}

export function clearRecent(): void {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // Same as above.
  }
}
