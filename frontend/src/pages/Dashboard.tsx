import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import * as api from "../api";
import type { Job, JobStatus, Stats, SourceStatus, PostedWithin } from "../api";
import JobCard from "../components/JobCard";
import ResumeUpload from "../components/ResumeUpload";

const STATUS_FILTERS: { value: JobStatus | "all"; label: string }[] = [
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
const POSTED_WINDOWS: { value: PostedWithin; label: string }[] = [
  { value: "1d", label: "Posted: Last 24 hours" },
  { value: "7d", label: "Posted: Last 7 days" },
  { value: "14d", label: "Posted: Last 14 days" },
  { value: "30d", label: "Posted: Last 30 days" },
];

export default function Dashboard() {
  const { user, logout, refreshUser } = useAuth();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [sources, setSources] = useState<SourceStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState("");
  // Newest-first by default: the API already returns them in that order,
  // and a stale-but-strong match is worth less than a fresh decent one.
  const [sort, setSort] = useState<"score" | "comp" | "posted">("posted");
  const [postedWithin, setPostedWithin] = useState<PostedWithin>("30d");
  // On by default: a preference the user set should change what they see, not
  // just the order. The count of what it hides is shown, with a way back.
  const [onlyMatches, setOnlyMatches] = useState(true);
  const [statusFilter, setStatusFilter] = useState<JobStatus | "all">("all");

  const load = async () => {
    setLoading(true);
    try {
      const [j, s] = await Promise.all([api.listJobs(postedWithin), api.getStats()]);
      setJobs(j);
      setStats(s);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    api.getSources().then(setSources).catch(() => setSources([]));
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

  const visibleJobs = useMemo(() => {
    let list = jobs.slice();
    if (onlyMatches) list = list.filter((j) => j.matches_preferences);
    if (statusFilter !== "all") list = list.filter((j) => j.status === statusFilter);
    if (query) {
      const q = query.toLowerCase();
      list = list.filter((j) => `${j.title} ${j.company}`.toLowerCase().includes(q));
    }
    if (sort === "score") list.sort((a, b) => b.score - a.score);
    else if (sort === "comp") {
      const annual = (j: Job) => (j.comp_unit === "hour" ? (j.comp_max ?? 0) * 2080 : j.comp_max ?? 0);
      list.sort((a, b) => annual(b) - annual(a));
    } else if (sort === "posted") list.sort((a, b) => (a.posted < b.posted ? 1 : -1));
    return list;
  }, [jobs, query, sort, statusFilter, onlyMatches]);

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

      <div className="controls">
        <input
          type="search"
          placeholder="Search title or company…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          value={postedWithin}
          aria-label="Posted within"
          onChange={(e) => setPostedWithin(e.target.value as PostedWithin)}
        >
          {POSTED_WINDOWS.map((w) => (
            <option key={w.value} value={w.value}>{w.label}</option>
          ))}
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)}>
          <option value="score">Sort: Match score</option>
          <option value="comp">Sort: Compensation</option>
          <option value="posted">Sort: Most recent</option>
        </select>
        <label className="checkbox-row inline">
          <input
            type="checkbox"
            checked={onlyMatches}
            onChange={(e) => setOnlyMatches(e.target.checked)}
          />
          <span>Only my preferences</span>
        </label>
        <div className="pill-group">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              className="pill"
              aria-pressed={statusFilter === f.value}
              onClick={() => setStatusFilter(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {!loading && onlyMatches && hiddenByPreferences > 0 && (
        <div className="filter-note">
          {hiddenByPreferences} {hiddenByPreferences === 1 ? "job doesn't" : "jobs don't"} match your
          preferences and {hiddenByPreferences === 1 ? "is" : "are"} hidden.{" "}
          <button className="btn-link" onClick={() => setOnlyMatches(false)}>Show them</button>
        </div>
      )}

      {loading ? (
        <div className="spinner-wrap">Loading your matches…</div>
      ) : visibleJobs.length === 0 ? (
        <div className="empty-state">
          {jobs.length === 0
            ? "Nothing posted in this window. Try a wider one, or hit Refresh jobs."
            : onlyMatches && hiddenByPreferences > 0
              ? "Nothing matches your preferences in this window. Widen them in Settings, or untick \u201cOnly my preferences\u201d."
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
