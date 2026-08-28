import { useState, type DragEvent } from "react";
import type { Job, JobStatus } from "../api";

/** The pipeline, in the order a job actually moves through it. */
const COLUMNS: { status: JobStatus; label: string; blurb: string }[] = [
  { status: "saved", label: "Saved", blurb: "Worth applying to" },
  { status: "applied", label: "Applied", blurb: "Application sent" },
  { status: "interviewing", label: "Interviewing", blurb: "In process" },
  { status: "offer", label: "Offer", blurb: "Offer received" },
  { status: "archived", label: "Archived", blurb: "Closed out" },
];

// Rejections belong at the end of the pipeline, but they are not the same
// event as archiving something yourself, so they share the column and keep
// their own label rather than being rewritten as "archived".
const TERMINAL: JobStatus[] = ["archived", "rejected"];

function columnFor(status: JobStatus): JobStatus | null {
  if (TERMINAL.includes(status)) return "archived";
  return COLUMNS.some((c) => c.status === status) ? status : null;
}

export default function KanbanBoard({
  jobs,
  onMove,
}: {
  jobs: Job[];
  onMove: (jobId: number, status: JobStatus) => void;
}) {
  const [dragging, setDragging] = useState<number | null>(null);
  const [over, setOver] = useState<JobStatus | null>(null);

  const onDrop = (e: DragEvent, status: JobStatus) => {
    e.preventDefault();
    setOver(null);
    // Read from the transfer rather than component state: state alone breaks
    // if a drag starts outside this component or the browser cancels it.
    const id = Number(e.dataTransfer.getData("text/plain")) || dragging;
    setDragging(null);
    if (id) onMove(id, status);
  };

  return (
    <div className="kanban">
      {COLUMNS.map((col) => {
        const inColumn = jobs.filter((j) => columnFor(j.status) === col.status);
        return (
          <section
            key={col.status}
            className={`kanban-col${over === col.status ? " drop-target" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setOver(col.status); }}
            onDragLeave={() => setOver((c) => (c === col.status ? null : c))}
            onDrop={(e) => onDrop(e, col.status)}
          >
            <header>
              <h3>{col.label} <span className="kanban-count">{inColumn.length}</span></h3>
              <p>{col.blurb}</p>
            </header>

            <div className="kanban-cards">
              {inColumn.length === 0 && <p className="kanban-empty">Nothing here yet.</p>}
              {inColumn.map((job) => (
                <article
                  key={job.id}
                  className={`kanban-card${dragging === job.id ? " dragging" : ""}`}
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData("text/plain", String(job.id));
                    e.dataTransfer.effectAllowed = "move";
                    setDragging(job.id);
                  }}
                  onDragEnd={() => { setDragging(null); setOver(null); }}
                >
                  <div className="kanban-card-title">{job.title}</div>
                  <div className="kanban-card-company">{job.company}</div>
                  <div className="kanban-card-meta">
                    <span className="kanban-score">{job.score}</span>
                    {job.location && <span>{job.location}</span>}
                    {job.status === "rejected" && <span className="tag-rejected">Rejected</span>}
                  </div>

                  {/* Dragging doesn't work with a keyboard or on touch, so the
                      select is the real control and the drag is the shortcut,
                      not the other way round. */}
                  {/* Labelled by stage rather than "Move to X": the select
                      shows the current value, so an action label reads as
                      "Move to Saved" on a card already in Saved. */}
                  <select
                    className="kanban-move"
                    aria-label={`Stage for ${job.title} at ${job.company}`}
                    value={job.status}
                    onChange={(e) => onMove(job.id, e.target.value as JobStatus)}
                  >
                    {COLUMNS.map((c) => (
                      <option key={c.status} value={c.status}>{c.label}</option>
                    ))}
                    {job.status === "rejected" && <option value="rejected">Rejected</option>}
                    <option value="new">Back to matches ↩</option>
                  </select>
                </article>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
