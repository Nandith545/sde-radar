import { useEffect, useId, useMemo, useRef, useState } from "react";

export interface CheckboxOption {
  value: string;
  label: string;
  /** Postings currently in this place. Shown so the list says where the jobs
   * are rather than offering 51 identical-looking rows. */
  count?: number;
  /** Marks an option that isn't part of the bundled list -- a value the user
   * saved before, kept visible so it can be seen and removed rather than
   * silently dropped. */
  custom?: boolean;
}

/**
 * A closed dropdown that opens onto a searchable list of checkboxes, with an
 * "all" row at the top.
 *
 * An empty selection *is* "all", rather than a separate stored value. That
 * keeps one meaning for the empty list all the way down to the column: the
 * API, the scoring and this control all read it as "don't narrow by this",
 * and there is no second state that has to be kept consistent with it.
 */
export default function CheckboxDropdown({
  label,
  allLabel,
  options,
  selected,
  onChange,
  searchPlaceholder,
  emptyText,
  disabled = false,
  hint,
}: {
  label: string;
  allLabel: string;
  options: CheckboxOption[];
  selected: string[];
  onChange: (next: string[]) => void;
  searchPlaceholder: string;
  emptyText: string;
  disabled?: boolean;
  hint?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const wrapRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const panelId = useId();

  // Clicking away and Escape both close. Without the first, the panel stays
  // over the rest of the form while you try to use it.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  useEffect(() => {
    if (open) searchRef.current?.focus();
    else setQuery("");
  }, [open]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options;
  }, [options, query]);

  const toggle = (value: string) =>
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);

  const summary = selected.length === 0
    ? allLabel
    : selected.length <= 2
      ? selected.map((v) => options.find((o) => o.value === v)?.label ?? v).join(", ")
      : `${selected.length} selected`;

  return (
    <div className="field checkbox-dropdown" ref={wrapRef}>
      <label id={`${panelId}-label`}>{label}</label>
      <button
        type="button"
        className="dropdown-toggle"
        aria-expanded={open}
        aria-controls={panelId}
        aria-labelledby={`${panelId}-label`}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
      >
        <span className={selected.length === 0 ? "dropdown-summary muted" : "dropdown-summary"}>
          {summary}
        </span>
        <span className="dropdown-caret" aria-hidden="true">▾</span>
      </button>

      {open && (
        <div className="dropdown-panel" id={panelId} role="group" aria-labelledby={`${panelId}-label`}>
          <input
            ref={searchRef}
            type="search"
            className="dropdown-search"
            placeholder={searchPlaceholder}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            // Enter would otherwise submit the surrounding preferences form
            // from inside the panel, saving and navigating mid-selection.
            onKeyDown={(e) => e.key === "Enter" && e.preventDefault()}
          />

          <label className="dropdown-option all">
            <input type="checkbox" checked={selected.length === 0} onChange={() => onChange([])} />
            <span>{allLabel}</span>
          </label>

          <div className="dropdown-scroll">
            {visible.length === 0 ? (
              <p className="dropdown-empty">{emptyText}</p>
            ) : (
              visible.map((o) => (
                <label className="dropdown-option" key={o.value}>
                  <input
                    type="checkbox"
                    checked={selected.includes(o.value)}
                    onChange={() => toggle(o.value)}
                  />
                  <span>{o.label}</span>
                  {o.custom ? (
                    <span className="dropdown-count custom">not in list</span>
                  ) : o.count !== undefined ? (
                    <span className={o.count > 0 ? "dropdown-count" : "dropdown-count zero"}>
                      {o.count}
                    </span>
                  ) : null}
                </label>
              ))
            )}
          </div>
        </div>
      )}

      {hint && <div className="field-hint">{hint}</div>}
    </div>
  );
}
