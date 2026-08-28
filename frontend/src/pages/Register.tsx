import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api";
import PasswordField from "../components/PasswordField";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
// Mirrors schemas.py: Field(min_length=8, max_length=128). Kept in sync by
// hand -- if the backend rule changes, change it here too, or the form will
// happily submit something the API rejects.
const PASSWORD_MIN = 8;

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
  const [touchedEmail, setTouchedEmail] = useState(false);
  const [touchedPassword, setTouchedPassword] = useState(false);

  const emailError = touchedEmail && email && !EMAIL_RE.test(email)
    ? "That doesn't look like an email address."
    : null;
  const passwordError = touchedPassword && password && password.length < PASSWORD_MIN
    ? `Passwords need at least ${PASSWORD_MIN} characters — that one has ${password.length}.`
    : null;

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
        {error && <div className="form-error" role="alert">{error}</div>}
        <form onSubmit={onSubmit} noValidate>
          <div className="field">
            <label htmlFor="fullName">Full name</label>
            <input
              id="fullName"
              required
              autoFocus
              autoComplete="name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              aria-invalid={emailError ? true : undefined}
              aria-describedby={emailError ? "email-error" : undefined}
              onChange={(e) => setEmail(e.target.value)}
              onBlur={() => setTouchedEmail(true)}
            />
            {emailError && <div className="field-error" id="email-error" role="alert">{emailError}</div>}
          </div>

          <PasswordField
            id="password"
            label="Password"
            value={password}
            onChange={setPassword}
            hint={`At least ${PASSWORD_MIN} characters. No other requirements — length beats symbols.`}
            error={passwordError}
            minLength={PASSWORD_MIN}
            autoComplete="new-password"
            onBlur={() => setTouchedPassword(true)}
          />

          <div className="field">
            <label htmlFor="city">Target city</label>
            <input id="city" required value={targetCity} onChange={(e) => setTargetCity(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="titles">Target titles</label>
            <input id="titles" required value={targetTitles} onChange={(e) => setTargetTitles(e.target.value)} />
            <div className="field-hint">Comma-separated, e.g. "Software Engineer, Backend Engineer".</div>
          </div>
          <button
            className="btn"
            type="submit"
            disabled={busy || !!emailError || !!passwordError}
            style={{ width: "100%" }}
          >
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
