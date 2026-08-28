import { useState, type FormEvent } from "react";
import * as api from "../api";
import { ApiError } from "../api";
import PasswordField from "./PasswordField";

/**
 * Sign-in address and password changes.
 *
 * Separate from the preferences form because these submit on their own and
 * have their own failure modes -- a rejected password shouldn't discard the
 * unsaved matching preferences sitting in the form next to it.
 */
export default function AccountSecurity({ email, onEmailChanged }: { email: string; onEmailChanged: () => void }) {
  const [newEmail, setNewEmail] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [emailBusy, setEmailBusy] = useState(false);
  const [emailMsg, setEmailMsg] = useState<string | null>(null);
  const [emailErr, setEmailErr] = useState<string | null>(null);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwBusy, setPwBusy] = useState(false);
  const [pwMsg, setPwMsg] = useState<string | null>(null);
  const [pwErr, setPwErr] = useState<string | null>(null);

  const mismatch = confirmPassword.length > 0 && newPassword !== confirmPassword;

  const submitEmail = async (e: FormEvent) => {
    e.preventDefault();
    setEmailErr(null);
    setEmailMsg(null);
    setEmailBusy(true);
    try {
      const { access_token } = await api.changeEmail(newEmail, emailPassword);
      // The old token is already dead server-side; store the replacement
      // before anything else re-renders and tries to use it.
      api.setToken(access_token, api.wasRemembered());
      setNewEmail("");
      setEmailPassword("");
      setEmailMsg("Sign-in address updated.");
      onEmailChanged();
    } catch (err) {
      setEmailErr(err instanceof ApiError ? err.message : "Could not change your email.");
    } finally {
      setEmailBusy(false);
    }
  };

  const submitPassword = async (e: FormEvent) => {
    e.preventDefault();
    setPwErr(null);
    setPwMsg(null);
    if (newPassword !== confirmPassword) {
      setPwErr("The two new passwords don't match.");
      return;
    }
    setPwBusy(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPwMsg("Password updated.");
    } catch (err) {
      setPwErr(err instanceof ApiError ? err.message : "Could not change your password.");
    } finally {
      setPwBusy(false);
    }
  };

  return (
    <>
      <section className="panel">
        <h2>Sign-in address</h2>
        {emailErr && <div className="form-error" role="alert">{emailErr}</div>}
        {emailMsg && !emailErr && <div className="form-success" role="status">{emailMsg}</div>}
        <p className="field-hint" style={{ marginBottom: 12 }}>Currently <strong>{email}</strong>.</p>
        <div className="field">
          <label htmlFor="acct-email">New email</label>
          <input
            id="acct-email"
            type="email"
            autoComplete="email"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </div>
        <PasswordField
          id="acct-email-password"
          label="Current password"
          value={emailPassword}
          onChange={setEmailPassword}
          autoComplete="current-password"
          hint="Confirms it's you, not just an open session."
        />
        <button
          className="btn secondary"
          type="button"
          onClick={submitEmail}
          disabled={emailBusy || !newEmail || !emailPassword}
        >
          {emailBusy ? "Updating…" : "Change email"}
        </button>
      </section>

      <section className="panel">
        <h2>Password</h2>
        {pwErr && <div className="form-error" role="alert">{pwErr}</div>}
        {pwMsg && !pwErr && <div className="form-success" role="status">{pwMsg}</div>}
        <PasswordField
          id="acct-current-password"
          label="Current password"
          value={currentPassword}
          onChange={setCurrentPassword}
          autoComplete="current-password"
        />
        <PasswordField
          id="acct-new-password"
          label="New password"
          value={newPassword}
          onChange={setNewPassword}
          minLength={8}
          autoComplete="new-password"
          hint="At least 8 characters."
        />
        <PasswordField
          id="acct-confirm-password"
          label="Confirm new password"
          value={confirmPassword}
          onChange={setConfirmPassword}
          autoComplete="new-password"
          error={mismatch ? "These don't match." : null}
        />
        <button
          className="btn secondary"
          type="button"
          onClick={submitPassword}
          disabled={pwBusy || !currentPassword || !newPassword || mismatch}
        >
          {pwBusy ? "Updating…" : "Change password"}
        </button>
        <p className="field-hint" style={{ marginTop: 10 }}>
          Tokens are stateless, so a change here doesn't sign out sessions on
          other devices. Those expire on their own.
        </p>
      </section>
    </>
  );
}
