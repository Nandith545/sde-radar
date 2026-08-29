import { useEffect, useRef, useState } from "react";
import * as api from "../api";
import { ApiError, type DocumentKind, type UserDocument } from "../api";

const KINDS: { value: DocumentKind; label: string }[] = [
  { value: "resume", label: "Resume" },
  { value: "cover_letter", label: "Cover letter" },
];

function sizeLabel(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * Every resume and cover letter the user has uploaded.
 *
 * Uploads add rather than replace, so this grows over time on purpose --
 * the version attached to an application months ago has to still be here
 * when the interview is scheduled.
 */
export default function DocumentLibrary({ onChange }: { onChange?: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [docs, setDocs] = useState<UserDocument[]>([]);
  const [kind, setKind] = useState<DocumentKind>("resume");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    api.listDocuments().then(setDocs).catch(() => setDocs([]));
  };
  useEffect(load, []);

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await api.uploadDocument(file, kind, label);
      setLabel("");
      load();
      onChange?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed. Try again.");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const remove = async (doc: UserDocument) => {
    setError(null);
    try {
      await api.deleteDocument(doc.id);
      load();
      onChange?.();
    } catch (err) {
      // A 409 here is the API refusing to orphan an application that points
      // at this file, and its message names how many. Worth showing verbatim.
      setError(err instanceof ApiError ? err.message : "Could not delete that file.");
    }
  };

  const download = async (doc: UserDocument) => {
    setError(null);
    try {
      await api.downloadDocument(doc);
    } catch {
      setError("Could not download that file.");
    }
  };

  return (
    <section className="panel">
      <h2>Documents</h2>
      {error && <div className="form-error" role="alert">{error}</div>}

      {docs.length === 0 ? (
        <p className="field-hint">
          Nothing uploaded yet. Add the resume and cover letter versions you send, and you
          can record which one went with each application.
        </p>
      ) : (
        <ul className="doc-list">
          {docs.map((doc) => (
            <li key={doc.id}>
              <div className="doc-main">
                <button className="btn-link" onClick={() => download(doc)}>
                  {doc.label || doc.filename}
                </button>
                <div className="field-hint">
                  {KINDS.find((k) => k.value === doc.kind)?.label} · {doc.filename} ·{" "}
                  {sizeLabel(doc.size_bytes)} · {new Date(doc.created_at).toLocaleDateString()}
                </div>
              </div>
              <button
                type="button"
                className="doc-remove"
                aria-label={`Delete ${doc.label || doc.filename}`}
                onClick={() => remove(doc)}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="doc-upload">
        <select value={kind} onChange={(e) => setKind(e.target.value as DocumentKind)} aria-label="Document type">
          {KINDS.map((k) => (
            <option key={k.value} value={k.value}>{k.label}</option>
          ))}
        </select>
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Label, e.g. Backend-heavy"
          aria-label="Label"
        />
        <input ref={fileRef} id="doc-file" type="file" accept=".pdf,.txt,.md" hidden onChange={onFile} />
        <label htmlFor="doc-file" className="btn secondary" style={{ display: "inline-block" }}>
          {busy ? "Uploading…" : "Add file"}
        </label>
      </div>
      <div className="field-hint">
        PDF, text or markdown, up to 5MB. Uploading never replaces an earlier version.
      </div>
    </section>
  );
}
