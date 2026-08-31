/** The client-side view controls, shared by the dashboard feed and the
 * per-board pages.
 *
 * These live here rather than in either page because the two have to agree:
 * a board page reached from the dashboard carries the dashboard's selections
 * in its URL, and it would be a bug if "Only my preferences" or a sort order
 * meant something different once you arrived.
 *
 * The age window is deliberately *not* one of these. It is applied by the
 * API, so changing it refetches rather than filtering what is already loaded.
 */
import type { Job, JobStatus, PostedWithin } from "./api";

export type JobSort = "score" | "comp" | "posted";

export interface JobFilters {
  query: string;
  sort: JobSort;
  status: JobStatus | "all";
  onlyMatches: boolean;
}

export const DEFAULT_FILTERS: JobFilters = {
  query: "",
  // Newest-first by default: the API already returns them in that order, and
  // a stale-but-strong match is worth less than a fresh decent one.
  sort: "posted",
  status: "all",
  // On by default: a preference the user set should change what they see, not
  // just the order. The count of what it hides is shown, with a way back.
  onlyMatches: true,
};

export const STATUS_FILTERS: { value: JobStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "new", label: "New" },
  { value: "saved", label: "Saved" },
  { value: "applied", label: "Applied" },
  { value: "interviewing", label: "Interviewing" },
  { value: "offer", label: "Offer" },
  { value: "rejected", label: "Rejected" },
];

// Capped at 30 days because the API refuses anything older, whatever is
// asked for. No "last hour": every connector truncates its timestamp to a
// date, so hour-level freshness is not something this data can support.
export const POSTED_WINDOWS: { value: PostedWithin; label: string }[] = [
  { value: "1d", label: "Posted: Last 24 hours" },
  { value: "7d", label: "Posted: Last 7 days" },
  { value: "14d", label: "Posted: Last 14 days" },
  { value: "30d", label: "Posted: Last 30 days" },
];

const POSTED_VALUES = POSTED_WINDOWS.map((w) => w.value);

/** The sentinel the API uses for "every board", and the segment the
 * all-boards route would carry. Kept in one place so the URL, the dropdown
 * and the query param can't drift apart. */
export const ALL_BOARDS = "all";

const ANNUAL_HOURS = 2080;

export function filterJobs(jobs: Job[], f: JobFilters): Job[] {
  let list = jobs.slice();
  if (f.onlyMatches) list = list.filter((j) => j.matches_preferences);
  if (f.status !== "all") list = list.filter((j) => j.status === f.status);
  if (f.query) {
    const q = f.query.toLowerCase();
    list = list.filter((j) => `${j.title} ${j.company}`.toLowerCase().includes(q));
  }
  if (f.sort === "score") list.sort((a, b) => b.score - a.score);
  else if (f.sort === "comp") {
    const annual = (j: Job) => (j.comp_unit === "hour" ? (j.comp_max ?? 0) * ANNUAL_HOURS : j.comp_max ?? 0);
    list.sort((a, b) => annual(b) - annual(a));
  } else if (f.sort === "posted") list.sort((a, b) => (a.posted < b.posted ? 1 : -1));
  return list;
}

/** Selections as URL query params, so a board page can be refreshed, shared
 * or reached with the back button and still show the same list. Defaults are
 * left out rather than spelled out, which keeps the common URL short. */
export function filtersToParams(f: JobFilters, postedWithin: PostedWithin): URLSearchParams {
  const params = new URLSearchParams();
  if (f.query) params.set("q", f.query);
  if (f.sort !== DEFAULT_FILTERS.sort) params.set("sort", f.sort);
  if (f.status !== DEFAULT_FILTERS.status) params.set("status", f.status);
  if (!f.onlyMatches) params.set("all_prefs", "1");
  if (postedWithin !== "30d") params.set("posted_within", postedWithin);
  return params;
}

/** The inverse. Anything unreadable falls back to its default -- a
 * hand-edited or truncated URL should show a sane list rather than an error. */
export function filtersFromParams(params: URLSearchParams): JobFilters {
  const sort = params.get("sort");
  const status = params.get("status");
  return {
    query: params.get("q") ?? DEFAULT_FILTERS.query,
    sort: sort === "score" || sort === "comp" || sort === "posted" ? sort : DEFAULT_FILTERS.sort,
    status: STATUS_FILTERS.some((s) => s.value === status)
      ? (status as JobStatus | "all")
      : DEFAULT_FILTERS.status,
    onlyMatches: params.get("all_prefs") !== "1",
  };
}

export function postedWithinFromParams(params: URLSearchParams): PostedWithin {
  const value = params.get("posted_within");
  return POSTED_VALUES.includes(value as PostedWithin) ? (value as PostedWithin) : "30d";
}
