import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api";
import PasswordField from "../components/PasswordField";
import ThemeToggle from "../components/ThemeToggle";

// Deliberately permissive: the backend's email-validator is the authority.
// This only catches the obvious "no @ at all" case while typing, so the
// field doesn't nag at someone halfway through their address.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Validation appears only after a field has been visited, so the form
  // doesn't show errors for fields nobody has filled in yet.
  const [touchedEmail, setTouchedEmail] = useState(false);

  const emailError = touchedEmail && email && !EMAIL_RE.test(email)
    ? "That doesn't look like an email address."
    : null;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password, remember);
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-wrap">
      <ThemeToggle />
      <div className="auth-card">
        <h1>Offerly</h1>
        <p className="sub">Sign in to your job pipeline.</p>
        {error && <div className="form-error" role="alert">{error}</div>}
        <form onSubmit={onSubmit} noValidate>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              required
              autoFocus
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
            autoComplete="current-password"
          />

          <label className="checkbox-row" htmlFor="remember">
            <input
              id="remember"
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
            />
            <span>Keep me signed in</span>
          </label>

          <button className="btn" type="submit" disabled={busy || !!emailError} style={{ width: "100%" }}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <div className="switch-link">
          New here? <Link to="/register">Create an account</Link>
        </div>
      </div>
    </div>
  );
}
