import type { JobSourceCount, JobStatus, PostedWithin } from "../api";
import { ALL_BOARDS, POSTED_WINDOWS, STATUS_FILTERS, type JobFilters, type JobSort } from "../jobFilters";

/** The controls bar above a list of jobs.
 *
 * One component for both the dashboard feed and the per-board pages: the
 * board dropdown is the only thing that behaves differently, and it does so
 * through `onSource` rather than through a variant of this component.
 */
export default function JobFilterBar({
  filters,
  onChange,
  postedWithin,
  onPostedWithin,
  boards,
  source,
  onSource,
}: {
  filters: JobFilters;
  onChange: (next: JobFilters) => void;
  postedWithin: PostedWithin;
  onPostedWithin: (next: PostedWithin) => void;
  boards: JobSourceCount[];
  /** The board currently being viewed, or ALL_BOARDS on the main feed. */
  source: string;
  onSource: (next: string) => void;
}) {
  const set = <K extends keyof JobFilters>(key: K, value: JobFilters[K]) =>
    onChange({ ...filters, [key]: value });

  // A board that has no postings in this window is still shown when it is
  // the one being viewed, so the dropdown never contradicts the page it sits
  // on by displaying some other board's name.
  const options = boards.some((b) => b.name === source)
    ? boards
    : source === ALL_BOARDS
      ? boards
      : [...boards, { name: source, count: 0 }];

  return (
    <div className="controls">
      <input
        type="search"
        placeholder="Search title or company…"
        value={filters.query}
        onChange={(e) => set("query", e.target.value)}
      />
      <select
        className="board-select"
        value={source}
        aria-label="Job board"
        onChange={(e) => onSource(e.target.value)}
      >
        <option value={ALL_BOARDS}>All job boards</option>
        {options.map((b) => (
          <option key={b.name} value={b.name}>
            {b.name} ({b.count})
          </option>
        ))}
      </select>
      <select
        value={postedWithin}
        aria-label="Posted within"
        onChange={(e) => onPostedWithin(e.target.value as PostedWithin)}
      >
        {POSTED_WINDOWS.map((w) => (
          <option key={w.value} value={w.value}>{w.label}</option>
        ))}
      </select>
      <select
        value={filters.sort}
        aria-label="Sort by"
        onChange={(e) => set("sort", e.target.value as JobSort)}
      >
        <option value="score">Sort: Match score</option>
        <option value="comp">Sort: Compensation</option>
        <option value="posted">Sort: Most recent</option>
      </select>
      <label className="checkbox-row inline">
        <input
          type="checkbox"
          checked={filters.onlyMatches}
          onChange={(e) => set("onlyMatches", e.target.checked)}
        />
        <span>Only my preferences</span>
      </label>
      <div className="pill-group">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            className="pill"
            aria-pressed={filters.status === f.value}
            onClick={() => set("status", f.value as JobStatus | "all")}
          >
            {f.label}
          </button>
        ))}
      </div>
    </div>
  );
}
