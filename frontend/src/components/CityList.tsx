import { useState, type KeyboardEvent } from "react";

/**
 * Add-one-at-a-time list of cities.
 *
 * A plain comma-separated text box can't work here: a city is already written
 * with a comma in it ("Seattle, WA"), so the separator and the data are the
 * same character. Each entry is committed on its own instead.
 */
export default function CityList({
  cities,
  onChange,
}: {
  cities: string[];
  onChange: (next: string[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const add = () => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    if (cities.some((c) => c.toLowerCase() === trimmed.toLowerCase())) {
      setError(`${trimmed} is already on the list.`);
      return;
    }
    setError(null);
    onChange([...cities, trimmed]);
    setDraft("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    // Enter would otherwise submit the surrounding preferences form, saving a
    // half-typed city and navigating away from the box.
    if (e.key === "Enter") {
      e.preventDefault();
      add();
    }
  };

  return (
    <div className="field">
      <label htmlFor="city-input">Cities</label>

      {cities.length > 0 && (
        <ul className="city-list">
          {cities.map((city) => (
            <li key={city}>
              <span>{city}</span>
              <button
                type="button"
                className="city-remove"
                aria-label={`Remove ${city}`}
                onClick={() => onChange(cities.filter((c) => c !== city))}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="city-add">
        <input
          id="city-input"
          value={draft}
          onChange={(e) => { setDraft(e.target.value); setError(null); }}
          onKeyDown={onKeyDown}
          placeholder="e.g. Seattle, WA"
          aria-describedby="city-hint"
        />
        <button type="button" className="btn secondary" onClick={add} disabled={!draft.trim()}>
          Add
        </button>
      </div>

      {error && <div className="field-error" role="alert">{error}</div>}
      <div className="field-hint" id="city-hint">
        {cities.length === 0
          ? "No cities set, so location is ignored. Add one to see only jobs there."
          : "Jobs outside these are hidden. Remote roles are always shown."}
      </div>
    </div>
  );
}
