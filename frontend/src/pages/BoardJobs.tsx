import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import * as api from "../api";
import { ApiError, type Job, type JobSourceCount, type JobStatus, type PostedWithin } from "../api";
import JobCard from "../components/JobCard";
import JobFilterBar from "../components/JobFilterBar";
import {
  ALL_BOARDS,
  filterJobs,
  filtersFromParams,
  filtersToParams,
  postedWithinFromParams,
  type JobFilters,
} from "../jobFilters";

/** One job board's postings, still scored and filtered by the user's own
 * preferences.
 *
 * A page rather than another tab on the dashboard, so a board is a place you
 * can link to, bookmark and come back to with the browser's back button. All
 * of the selections live in the URL for the same reason -- reloading a board
 * page you have narrowed down should not throw the narrowing away.
 */
export default function BoardJobs() {
  const { source = ALL_BOARDS } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const filters = useMemo<JobFilters>(() => filtersFromParams(searchParams), [searchParams]);
  const postedWithin = useMemo(() => postedWithinFromParams(searchParams), [searchParams]);

  const [jobs, setJobs] = useState<Job[]>([]);
  const [boards, setBoards] = useState<JobSourceCount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Writing selections back into the URL rather than into component state
  // keeps one copy of them: the address bar always describes what is on
  // screen, and the back button steps through the narrowing.
  const applyFilters = (next: JobFilters, window: PostedWithin = postedWithin) =>
    setSearchParams(filtersToParams(next, window), { replace: true });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [listed, facets] = await Promise.all([
        api.listJobs(postedWithin, source),
        api.listJobSources(postedWithin),
      ]);
      setJobs(listed);
      setBoards(facets);
    } catch (e) {
      // A 422 here means the URL names a board that does not exist -- a
      // typo, or a connector removed since the link was made. That is worth
      // saying plainly, because it looks identical to a quiet board.
      setError(
        e instanceof ApiError && e.status === 422
          ? `There's no job board called “${source}”.`
          : "Could not load this board. Try again in a moment.",
      );
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }, [postedWithin, source]);

  useEffect(() => {
    load();
  }, [load]);

  const onUpdate = async (jobId: number, patch: { status?: JobStatus; notes?: string }) => {
    const updated = await api.updateMatch(jobId, patch);
    setJobs((prev) => prev.map((j) => (j.id === jobId ? updated : j)));
  };

  const onSource = (next: string) => {
    const query = filtersToParams(filters, postedWithin).toString();
    const suffix = query ? `?${query}` : "";
    navigate(next === ALL_BOARDS ? `/${suffix}` : `/boards/${next}${suffix}`);
  };

  const visibleJobs = useMemo(() => filterJobs(jobs, filters), [jobs, filters]);
  const hiddenByPreferences = jobs.filter((j) => !j.matches_preferences).length;

  if (!user) return null;

  return (
    <div className="shell">
      <div className="topbar">
        <div className="brand">
          <div>
            <div className="tag">
              {user.target_cities.length ? user.target_cities.join(" · ") : "Anywhere"} · Matched to your resume
            </div>
            <h1 className="board-title">
              <span className="board-name">{source}</span>
            </h1>
          </div>
        </div>
        <div className="user-menu">
          <Link className="btn ghost" to="/">← All boards</Link>
          <Link className="btn ghost" to="/settings">Settings</Link>
        </div>
      </div>

      <p className="board-blurb">
        {loading
          ? "Loading…"
          : error
            ? ""
            : `${jobs.length} ${jobs.length === 1 ? "posting" : "postings"} from ${source} in this window, scored against your resume and preferences.`}
      </p>

      <JobFilterBar
        filters={filters}
        onChange={applyFilters}
        postedWithin={postedWithin}
        onPostedWithin={(w) => applyFilters(filters, w)}
        boards={boards}
        source={source}
        onSource={onSource}
      />

      {!loading && !error && filters.onlyMatches && hiddenByPreferences > 0 && (
        <div className="filter-note">
          {hiddenByPreferences} {hiddenByPreferences === 1 ? "job doesn't" : "jobs don't"} match your
          preferences and {hiddenByPreferences === 1 ? "is" : "are"} hidden.{" "}
          <button className="btn-link" onClick={() => applyFilters({ ...filters, onlyMatches: false })}>
            Show them
          </button>
        </div>
      )}

      {loading ? (
        <div className="spinner-wrap">Loading {source} jobs…</div>
      ) : error ? (
        <div className="empty-state">
          {error} <Link className="btn-link" to="/">Back to all boards</Link>
        </div>
      ) : visibleJobs.length === 0 ? (
        <div className="empty-state">
          {jobs.length === 0
            ? `Nothing from ${source} in this window. Try a wider one, or pick another board.`
            : filters.onlyMatches && hiddenByPreferences > 0
              ? "Nothing here matches your preferences. Widen them in Settings, or untick “Only my preferences”."
              : "No jobs match this filter yet."}
        </div>
      ) : (
        <div className="cards">
          {visibleJobs.map((job, i) => (
            <JobCard key={job.id} job={job} rank={i + 1} onUpdate={onUpdate} />
          ))}
        </div>
      )}
    </div>
  );
}
