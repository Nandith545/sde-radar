import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [targetCity, setTargetCity] = useState("Seattle, WA");
  const [targetTitles, setTargetTitles] = useState("Software Engineer, Backend Engineer, Full Stack Engineer");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await register({ email, password, full_name: fullName, target_city: targetCity, target_titles: targetTitles });
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h1>SDE Radar</h1>
        <p className="sub">Create your account — resume-matched jobs in under a minute.</p>
        {error && <div className="form-error">{error}</div>}
        <form onSubmit={onSubmit}>
          <div className="field">
            <label htmlFor="fullName">Full name</label>
            <input id="fullName" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input id="password" type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
            <div className="field-hint">At least 8 characters.</div>
          </div>
          <div className="field">
            <label htmlFor="city">Target city</label>
            <input id="city" required value={targetCity} onChange={(e) => setTargetCity(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="titles">Target titles</label>
            <input id="titles" required value={targetTitles} onChange={(e) => setTargetTitles(e.target.value)} />
            <div className="field-hint">Comma-separated, e.g. "Software Engineer, Backend Engineer".</div>
          </div>
          <button className="btn" type="submit" disabled={busy} style={{ width: "100%" }}>
            {busy ? "Creating account…" : "Create account"}
          </button>
        </form>
        <div className="switch-link">
          Already have an account? <Link to="/login">Sign in</Link>
        </div>
      </div>
    </div>
  );
}
