import { useRef, useState } from "react";
import * as api from "../api";
import { ApiError } from "../api";

interface Props {
  cities: string[];
  titles: string;
  onUploaded: () => void;
}

/**
 * First-run onboarding: search targets plus the resume, in one step.
 *
 * City and titles used to live on the register form, pre-filled with
 * "Seattle, WA". Anyone who didn't notice silently got Seattle results with
 * nothing on screen explaining why. They belong here instead, at the moment
 * the user is about to receive matches and can see what they affect --
 * which also keeps sign-up down to name, email and password.
 */
// Cities are a list now, so "unset" is simply an empty one -- no sentinel
// value to compare against. Titles are still a string, and the backend fills
// in a default the register form never asked for, so that one still needs a
// sentinel to avoid showing a pre-filled guess the user might not read.
const UNSET_TITLES = "Software Engineer";

export default function ResumeUpload({ cities, titles, onUploaded }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [targetCity, setTargetCity] = useState(cities[0] ?? "");
  const [targetTitles, setTargetTitles] = useState(titles === UNSET_TITLES ? "" : titles);

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      // Save the targets first: scoring reads them when the upload triggers
      // a rematch, so writing them afterwards would score this first batch
      // against the old values.
      if (targetCity !== (cities[0] ?? "") || targetTitles !== titles) {
        await api.updateMe({
          target_cities: targetCity.trim() ? [targetCity.trim()] : [],
          target_titles: targetTitles,
        });
      }
      await api.uploadResume(file);
      onUploaded();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed. Try again.");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div className="resume-banner onboarding">
      <div className="onboarding-intro">
        <strong>Upload your resume to get matched jobs</strong>
        <p>PDF or plain text. We only extract skills and years of experience — nothing is shared.</p>
      </div>

      <div className="onboarding-targets">
        <div className="field">
          <label htmlFor="onboard-city">Target city</label>
          <input
            id="onboard-city"
            value={targetCity}
            onChange={(e) => setTargetCity(e.target.value)}
            placeholder="e.g. Seattle, WA"
          />
        </div>
        <div className="field">
          <label htmlFor="onboard-titles">Target titles</label>
          <input
            id="onboard-titles"
            value={targetTitles}
            onChange={(e) => setTargetTitles(e.target.value)}
            placeholder="e.g. Software Engineer, Backend Engineer"
          />
          <div className="field-hint">Comma-separated. Used to boost matching titles.</div>
        </div>
      </div>

      {error && <p className="onboarding-error">{error}</p>}

      <div className="onboarding-action">
        <input ref={inputRef} type="file" accept=".pdf,.txt,.md" hidden onChange={onFileChange} id="resume-file" />
        <label htmlFor="resume-file" className="btn" style={{ display: "inline-block" }}>
          {busy ? "Uploading…" : "Upload resume"}
        </label>
      </div>
    </div>
  );
}
