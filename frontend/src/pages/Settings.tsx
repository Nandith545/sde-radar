import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import * as api from "../api";
import { ApiError, type WorkMode } from "../api";

const WORK_MODES: { value: WorkMode; label: string; blurb: string }[] = [
  { value: "", label: "No preference", blurb: "Score every posting the same way." },
  { value: "remote", label: "Remote", blurb: "Boost remote roles, flag ones that aren't." },
  { value: "hybrid", label: "Hybrid", blurb: "Boost roles that split office and home." },
  { value: "onsite", label: "Onsite", blurb: "Boost roles based in an office." },
];

export default function Settings() {
  const { user, refreshUser, logout } = useAuth();
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);

  const [fullName, setFullName] = useState("");
  const [country, setCountry] = useState("");
  const [city, setCity] = useState("");
  const [titles, setTitles] = useState("");
  const [workMode, setWorkMode] = useState<WorkMode>("");

  const [resume, setResume] = useState<api.Resume | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Seed the form from the server rather than from a render-time default, so
  // a reload can never show stale values as if they were saved.
  useEffect(() => {
    if (!user) return;
    setFullName(user.full_name);
    setCountry(user.target_country);
    setCity(user.target_city);
    setTitles(user.target_titles);
    setWorkMode(user.work_mode);
  }, [user]);

  useEffect(() => {
    api.getResume().then(setResume).catch(() => setResume(null));
  }, []);

  if (!user) return null;

  const onSave = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);
    setSaved(false);
    try {
      await api.updateMe({
        full_name: fullName,
        target_city: city,
        target_titles: titles,
        target_country: country,
        work_mode: workMode,
      });
      await refreshUser();
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save. Try again.");
    } finally {
      setSaving(false);
    }
  };

  const onResumeChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      setResume(await api.uploadResume(file));
      await refreshUser();
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed. Try again.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="shell">
      <div className="topbar">
        <div className="brand">
          <div>
            <div className="tag">Profile &amp; matching preferences</div>
            <h1>Settings</h1>
          </div>
        </div>
        <div className="user-menu">
          <Link className="btn secondary" to="/">Back to jobs</Link>
          <button className="btn ghost" onClick={() => { logout(); navigate("/login"); }}>
            Sign out
          </button>
        </div>
      </div>

      {error && <div className="form-error" role="alert">{error}</div>}
      {saved && !error && <div className="form-success" role="status">Saved. Matching updates on your next refresh.</div>}

      <form className="settings-grid" onSubmit={onSave}>
        <section className="panel">
          <h2>Profile</h2>
          <div className="field">
            <label htmlFor="set-name">Full name</label>
            <input id="set-name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="set-email">Email</label>
            <input id="set-email" value={user.email} disabled />
            <div className="field-hint">Sign-in address. Changing it isn't supported yet.</div>
          </div>
        </section>

        <section className="panel">
          <h2>Where you want to work</h2>
          <div className="field">
            <label htmlFor="set-country">Country</label>
            <input
              id="set-country"
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              placeholder="e.g. United States"
            />
            <div className="field-hint">
              Postings elsewhere get flagged and scored down. Left blank, country is ignored.
            </div>
          </div>
          <div className="field">
            <label htmlFor="set-city">City</label>
            <input
              id="set-city"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              placeholder="e.g. Seattle, WA"
            />
            <div className="field-hint">A match here is a bonus, not a filter.</div>
          </div>

          <fieldset className="field mode-set">
            <legend>Work mode</legend>
            {WORK_MODES.map((m) => (
              <label key={m.value || "any"} className="mode-option">
                <input
                  type="radio"
                  name="work-mode"
                  value={m.value}
                  checked={workMode === m.value}
                  onChange={() => setWorkMode(m.value)}
                />
                <span>
                  <strong>{m.label}</strong>
                  <em>{m.blurb}</em>
                </span>
              </label>
            ))}
            <div className="field-hint">
              Boards don't publish this as a field, so it's read from the posting's
              text. Anything unreadable is left alone rather than guessed at.
            </div>
          </fieldset>
        </section>

        <section className="panel">
          <h2>What you want to do</h2>
          <div className="field">
            <label htmlFor="set-titles">Target roles</label>
            <input
              id="set-titles"
              value={titles}
              onChange={(e) => setTitles(e.target.value)}
              placeholder="e.g. Software Engineer, Backend Engineer"
            />
            <div className="field-hint">Comma-separated. A title match adds to the score.</div>
          </div>
        </section>

        <section className="panel">
          <h2>Resume</h2>
          {resume ? (
            <div className="resume-summary">
              <div><strong>{resume.filename}</strong></div>
              <div className="field-hint">
                {resume.skills.length} skills detected
                {resume.years_experience != null && ` · ${resume.years_experience} years experience`}
              </div>
              <div className="chips">
                {resume.skills.slice(0, 12).map((s) => <span className="chip" key={s}>{s}</span>)}
                {resume.skills.length > 12 && <span className="chip muted">+{resume.skills.length - 12}</span>}
              </div>
            </div>
          ) : (
            <p className="field-hint">No resume yet. Skill overlap drives most of the score, so this matters more than anything else on this page.</p>
          )}
          <input ref={fileRef} id="set-resume" type="file" accept=".pdf,.txt,.md" hidden onChange={onResumeChange} />
          <label htmlFor="set-resume" className="btn secondary" style={{ display: "inline-block", marginTop: 10 }}>
            {uploading ? "Uploading…" : resume ? "Replace resume" : "Upload resume"}
          </label>
        </section>

        <div className="settings-actions">
          <button className="btn" type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save preferences"}
          </button>
        </div>
      </form>
    </div>
  );
}
