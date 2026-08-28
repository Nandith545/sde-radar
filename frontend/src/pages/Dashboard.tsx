import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../context/AuthContext";
import * as api from "../api";
import type { Job, JobStatus, Stats, SourceStatus } from "../api";
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

export default function Dashboard() {
  const { user, logout, refreshUser } = useAuth();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [sources, setSources] = useState<SourceStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"score" | "comp" | "posted">("score");
  const [statusFilter, setStatusFilter] = useState<JobStatus | "all">("all");

  const load = async () => {
    setLoading(true);
    try {
      const [j, s] = await Promise.all([api.listJobs(), api.getStats()]);
      setJobs(j);
      setStats(s);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    api.getSources().then(setSources).catch(() => setSources([]));
  }, []);

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
  }, [jobs, query, sort, statusFilter]);

  if (!user) return null;

  return (
    <div className="shell">
      <div className="topbar">
        <div className="brand">
          <div>
            <div className="tag">{user.target_city} · Matched to your resume</div>
            <h1>SDE Radar</h1>
          </div>
        </div>
        <div className="user-menu">
          <span>{user.full_name}</span>
          <button className="btn secondary" onClick={onRefreshJobs} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh jobs"}
          </button>
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

      {!user.has_resume && <ResumeUpload onUploaded={() => { refreshUser(); load(); }} />}

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
        <select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)}>
          <option value="score">Sort: Match score</option>
          <option value="comp">Sort: Compensation</option>
          <option value="posted">Sort: Most recent</option>
        </select>
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

      {loading ? (
        <div className="spinner-wrap">Loading your matches…</div>
      ) : visibleJobs.length === 0 ? (
        <div className="empty-state">No jobs match this filter yet.</div>
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
