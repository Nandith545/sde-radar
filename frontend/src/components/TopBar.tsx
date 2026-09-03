import type { ReactNode } from "react";
import ThemeToggle from "./ThemeToggle";

interface TopBarProps {
  /** The small uppercase line above the heading. */
  tag: ReactNode;
  /** A node rather than a string: the board page needs its own <h1> markup. */
  heading: ReactNode;
  /** Page-specific actions, rendered before the theme toggle. */
  children?: ReactNode;
}

/** The header every signed-in page shares. It was copy-pasted into three
 *  pages, which is why the theme toggle now lives here: one control, one
 *  place to change it. */
export default function TopBar({ tag, heading, children }: TopBarProps) {
  return (
    <div className="topbar">
      <div className="brand">
        <div>
          <div className="tag">{tag}</div>
          {heading}
        </div>
      </div>
      <div className="user-menu">
        {children}
        <ThemeToggle />
      </div>
    </div>
  );
}
