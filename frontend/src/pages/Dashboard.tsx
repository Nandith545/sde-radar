import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import * as api from "../api";
import KanbanBoard from "../components/KanbanBoard";
import type { Job, JobSourceCount, JobStatus, Stats, SourceStatus, PostedWithin, UserDocument } from "../api";
import JobCard from "../components/JobCard";
import JobFilterBar from "../components/JobFilterBar";
import ResumeUpload from "../components/ResumeUpload";
import {
  ALL_BOARDS,
  filterJobs,
  filtersFromParams,
  filtersToParams,
  postedWithinFromParams,
  type JobFilters,
} from "../jobFilters";

export default function Dashboard() {
  const { user, logout, refreshUser } = useAuth();
  const navigate = useNavigate();
  // Selections live in the URL, not in state, so they survive a reload and
  // can be handed to a board page and back again unchanged.
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo<JobFilters>(() => filtersFromParams(searchParams), [searchParams]);
  const postedWithin = useMemo(() => postedWithinFromParams(searchParams), [searchParams]);

  const [jobs, setJobs] = useState<Job[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [sources, setSources] = useState<SourceStatus[]>([]);
  const [boards, setBoards] = useState<JobSourceCount[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  // Two views over the same data: "matches" is the incoming feed, "board" is
  // the pipeline of jobs already acted on. A job leaves one by entering the
  // other, so they are tabs rather than filters.
  const [view, setView] = useState<"matches" | "board">("matches");
  const [documents, setDocuments] = useState<UserDocument[]>([]);

  const applyFilters = (next: JobFilters, window: PostedWithin = postedWithin) =>
    setSearchParams(filtersToParams(next, window), { replace: true });

  const load = async () => {
    setLoading(true);
    try {
      const [j, s, b] = await Promise.all([
        api.listJobs(postedWithin),
        api.getStats(),
        api.listJobSources(postedWithin),
      ]);
      setJobs(j);
      setStats(s);
      setBoards(b);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    api.getSources().then(setSources).catch(() => setSources([]));
    api.listDocuments().then(setDocuments).catch(() => setDocuments([]));
  }, []);

  // The age window is applied by the API, not in the browser, so changing it
  // has to refetch rather than filter what's already on screen.
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [postedWithin]);

  const onUpdate = async (jobId: number, patch: { status?: JobStatus; notes?: string }) => {
    const updated = await api.updateMatch(jobId, patch);
    setJobs((prev) => prev.map((j) => (j.id === jobId ? updated : j)));
    const s = await api.getStats();
    setStats(s);
  };

  const onRefreshJobs = async () => {
    setRefreshing(true);
    try {
      await api.refreshJobs();
      await load();
    } finally {
      setRefreshing(false);
    }
  };

  // Picking a board leaves the feed for that board's own page, carrying the
  // current selections so the list arrives narrowed the same way.
  const onSource = (next: string) => {
    if (next === ALL_BOARDS) return;
    const query = filtersToParams(filters, postedWithin).toString();
    navigate(`/boards/${next}${query ? `?${query}` : ""}`);
  };

  const visibleJobs = useMemo(() => filterJobs(jobs, filters), [jobs, filters]);

  const hiddenByPreferences = jobs.filter((j) => !j.matches_preferences).length;
  // Anything the user has touched belongs on the board, whatever the current
  // match filters say -- a saved job must not vanish because the city changed.
  const trackedJobs = jobs.filter((j) => j.status !== "new");

  if (!user) return null;

  return (
    <div className="shell">
      <div className="topbar">
        <div className="brand">
          <div>
            <div className="tag">
              {user.target_cities.length ? user.target_cities.join(" · ") : "Anywhere"} · Matched to your resume
            </div>
            <h1>SDE Radar</h1>
          </div>
        </div>
        <div className="user-menu">
          <span>{user.full_name}</span>
          <button className="btn secondary" onClick={onRefreshJobs} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh jobs"}
          </button>
          <Link className="btn ghost" to="/settings">Settings</Link>
          <button className="btn ghost" onClick={logout}>
            Sign out
          </button>
        </div>
      </div>

      {sources.length > 0 && (
        <div className="connector-strip">
          <span className="connector-label">Job boards:</span>
          {sources.map((s) => (
            <span
              key={s.name}
              className={`connector-pill${s.active ? " active" : " inactive"}`}
              title={s.active ? `${s.name} connector is live` : `${s.name} connector needs API credentials`}
            >
              <span className="dot" />
              {s.name}
            </span>
          ))}
        </div>
      )}

      {!user.has_resume && (
        <ResumeUpload
          cities={user.target_cities}
          titles={user.target_titles}
          onUploaded={() => { refreshUser(); load(); }}
        />
      )}

      {stats && (
        <div className="stats">
          <div className="stat">
            <div className="n">{stats.total}</div>
            <div className="l">Tracked</div>
          </div>
          <div className="stat">
            <div className="n">{stats.avg_score}</div>
            <div className="l">Avg match</div>
          </div>
          <div className="stat">
            <div className="n">{stats.applied}</div>
            <div className="l">Applied</div>
          </div>
          <div className="stat">
            <div className="n">{stats.interviewing}</div>
            <div className="l">Interviewing</div>
          </div>
          <div className="stat">
            <div className="n">{stats.offers}</div>
            <div className="l">Offers</div>
          </div>
        </div>
      )}

      <div className="view-tabs" role="tablist">
        <button
          role="tab"
          aria-selected={view === "matches"}
          className="view-tab"
          onClick={() => setView("matches")}
        >
          Matches
        </button>
        <button
          role="tab"
          aria-selected={view === "board"}
          className="view-tab"
          onClick={() => setView("board")}
        >
          Board <span className="kanban-count">{trackedJobs.length}</span>
        </button>
      </div>

      {view === "matches" && (
        <JobFilterBar
          filters={filters}
          onChange={applyFilters}
          postedWithin={postedWithin}
          onPostedWithin={(w) => applyFilters(filters, w)}
          boards={boards}
          source={ALL_BOARDS}
          onSource={onSource}
        />
      )}

      {!loading && view === "matches" && filters.onlyMatches && hiddenByPreferences > 0 && (
        <div className="filter-note">
          {hiddenByPreferences} {hiddenByPreferences === 1 ? "job doesn't" : "jobs don't"} match your
          preferences and {hiddenByPreferences === 1 ? "is" : "are"} hidden.{" "}
          <button className="btn-link" onClick={() => applyFilters({ ...filters, onlyMatches: false })}>
            Show them
          </button>
        </div>
      )}

      {loading ? (
        <div className="spinner-wrap">Loading your matches…</div>
      ) : view === "board" ? (
        trackedJobs.length === 0 ? (
          <div className="empty-state">
            Nothing on the board yet. Save a job from Matches and it appears here.
          </div>
        ) : (
          <KanbanBoard
            jobs={trackedJobs}
            documents={documents}
            onMove={(id, status) => onUpdate(id, { status })}
            onAttach={(id, field, value) => onUpdate(id, { [field]: value })}
          />
        )
      ) : visibleJobs.length === 0 ? (
        <div className="empty-state">
          {jobs.length === 0
            ? "Nothing posted in this window. Try a wider one, or hit Refresh jobs."
            : filters.onlyMatches && hiddenByPreferences > 0
              ? "Nothing matches your preferences in this window. Widen them in Settings, or untick “Only my preferences”."
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
