import { useState, type ChangeEvent, type KeyboardEvent } from "react";

interface Props {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Shown under the field when empty, e.g. the rules on the register form. */
  hint?: string;
  /** Validation message to show once the user has left the field. */
  error?: string | null;
  minLength?: number;
  autoComplete: "current-password" | "new-password";
  autoFocus?: boolean;
  onBlur?: () => void;
}

/**
 * Password input with a reveal toggle and a Caps Lock warning.
 *
 * Both exist for the same reason: a mistyped password is indistinguishable
 * from a wrong one once it's masked, and "invalid credentials" is a poor way
 * to discover that Caps Lock was on.
 */
export default function PasswordField({
  id, label, value, onChange, hint, error, minLength, autoComplete, autoFocus, onBlur,
}: Props) {
  const [revealed, setRevealed] = useState(false);
  const [capsLock, setCapsLock] = useState(false);

  // getModifierState is only meaningful on a real key event, so this tracks
  // keyboard activity in the field rather than polling anything global.
  const trackCapsLock = (e: KeyboardEvent<HTMLInputElement>) => {
    setCapsLock(e.getModifierState("CapsLock"));
  };

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="password-wrap">
        <input
          id={id}
          type={revealed ? "text" : "password"}
          required
          minLength={minLength}
          autoComplete={autoComplete}
          autoFocus={autoFocus}
          value={value}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
          onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
          onKeyUp={trackCapsLock}
          onKeyDown={trackCapsLock}
          onBlur={() => { setCapsLock(false); onBlur?.(); }}
        />
        <button
          type="button"
          className="reveal-btn"
          // Not a submit button, and not part of the tab order to the submit
          // button -- keyboard users tab from password straight to sign in.
          tabIndex={-1}
          aria-label={revealed ? "Hide password" : "Show password"}
          aria-pressed={revealed}
          onClick={() => setRevealed((r) => !r)}
        >
          {revealed ? "Hide" : "Show"}
        </button>
      </div>
      {capsLock && (
        <div className="field-warning" role="status">
          Caps Lock is on.
        </div>
      )}
      {error ? (
        <div className="field-error" id={`${id}-error`} role="alert">{error}</div>
      ) : (
        hint && <div className="field-hint" id={`${id}-hint`}>{hint}</div>
      )}
    </div>
  );
}
