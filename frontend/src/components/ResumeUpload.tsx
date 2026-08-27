import { useRef, useState } from "react";
import * as api from "../api";
import { ApiError } from "../api";

export default function ResumeUpload({ onUploaded }: { onUploaded: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
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
    <div className="resume-banner">
      <div>
        <strong>Upload your resume to get matched jobs</strong>
        <p>PDF or plain text. We only extract skills and years of experience — nothing is shared.</p>
        {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
      </div>
      <div>
        <input ref={inputRef} type="file" accept=".pdf,.txt,.md" hidden onChange={onFileChange} id="resume-file" />
        <label htmlFor="resume-file" className="btn" style={{ display: "inline-block" }}>
          {busy ? "Uploading…" : "Upload resume"}
        </label>
      </div>
    </div>
  );
}
