import { useTheme } from "../context/ThemeContext";

/** Light/dark switch. A button rather than a checkbox: the state is binary,
 *  and aria-pressed says which way it is set without needing a visible label. */
export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";
  const label = isDark ? "Switch to light theme" : "Switch to dark theme";

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggleTheme}
      aria-pressed={isDark}
      aria-label={label}
      title={label}
    >
      <span className="ic sun" aria-hidden="true">
        ☀
      </span>
      <span className="ic moon" aria-hidden="true">
        ☾
      </span>
      <span className="thumb" aria-hidden="true" />
    </button>
  );
}
