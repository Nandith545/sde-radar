import { useState } from "react";
import type { Job, JobStatus } from "../api";

const STATUS_LABELS: Record<JobStatus, string> = {
  new: "New",
  saved: "Saved",
  applied: "Applied",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Rejected",
  archived: "Archived",
};

function scoreTier(score: number): "high" | "mid" | "low" {
  if (score >= 85) return "high";
  if (score >= 65) return "mid";
  return "low";
}

function fmtComp(job: Job): string {
  if (!job.comp_min) return "Not listed";
  const isHour = job.comp_unit === "hour";
  const fmt = (n: number) => (isHour ? `$${n}` : `$${Math.round(n / 1000)}K`);
  return `${fmt(job.comp_min)}–${fmt(job.comp_max ?? job.comp_min)}${isHour ? "/hr" : "/yr"}`;
}

function fmtDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00Z");
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

export default function JobCard({
  job,
  rank,
  onUpdate,
}: {
  job: Job;
  rank: number;
  onUpdate: (jobId: number, patch: { status?: JobStatus; notes?: string }) => void;
}) {
  const [notesOpen, setNotesOpen] = useState(false);
  const [notesDraft, setNotesDraft] = useState(job.notes);
  const tier = scoreTier(job.score);

  return (
    <div className="card">
      <div className="card-top">
        <div className="rank mono">{String(rank).padStart(2, "0")}</div>
        <div className="card-head">
          <h2>{job.title}</h2>
          <div className="company">
            {job.company} · {job.location}
          </div>
        </div>
        <div className="score">
          <div className="num" data-tier={tier}>
            {job.score}
          </div>
          <div className="lab">match</div>
        </div>
      </div>
      <div className="meta">
        <span>{fmtComp(job)}</span>
        <span>{job.job_type}</span>
        <span>Posted {fmtDate(job.posted)}</span>
      </div>
      {job.sources && job.sources.length > 0 && (
        <div className="sources">
          {job.sources.map((s) => (
            <span className="source-badge" key={s}>
              {s}
            </span>
          ))}
          {job.sources.length > 1 && <span className="source-note">seen on {job.sources.length} boards</span>}
        </div>
      )}
      {job.skills.length > 0 && (
        <div className="chips">
          {job.skills.map((s) => (
            <span className="chip" key={s}>
              {s}
            </span>
          ))}
        </div>
      )}
      <p className="reason">{job.reason}</p>
      {job.flag && (
        <div className="flag">
          <span className="ic">⚠</span>
          <span>{job.flag}</span>
        </div>
      )}
      <div className="card-actions">
        <select
          className="status-select"
          value={job.status}
          onChange={(e) => onUpdate(job.id, { status: e.target.value as JobStatus })}
        >
          {(Object.keys(STATUS_LABELS) as JobStatus[]).map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </select>
        <div className="right-actions">
          <button className="btn ghost" onClick={() => setNotesOpen((o) => !o)}>
            {notesOpen ? "Hide notes" : job.notes ? "Edit notes" : "Add notes"}
          </button>
          <a className="btn-link" href={job.url} target="_blank" rel="noopener noreferrer">
            Apply ↗
          </a>
        </div>
      </div>
      {notesOpen && (
        <div className="notes-area">
          <textarea
            placeholder="Recruiter contact, referral status, interview notes…"
            value={notesDraft}
            onChange={(e) => setNotesDraft(e.target.value)}
            onBlur={() => {
              if (notesDraft !== job.notes) onUpdate(job.id, { notes: notesDraft });
            }}
          />
        </div>
      )}
    </div>
  );
}
