import { useEffect, useMemo, useState } from "react";
import * as api from "../api";
import type { RegionCountry, RegionCountryDetail } from "../api";
import CheckboxDropdown, { type CheckboxOption } from "./CheckboxDropdown";

/**
 * Country -> state/province -> city, each tier narrowing the next.
 *
 * The cascade is the point: picking states restricts which cities are on
 * offer, and a city already chosen that no longer belongs to any selected
 * state is dropped as the selection changes. Leaving it behind would keep a
 * filter running that the control no longer shows.
 *
 * Cities the user saved before this picker existed -- the old box took free
 * text -- are kept and marked rather than discarded. Silently dropping a
 * saved preference looks exactly like the app forgetting a setting.
 */
export default function RegionPicker({
  country,
  states,
  cities,
  onChange,
}: {
  country: string;
  states: string[];
  cities: string[];
  onChange: (next: { country: string; states: string[]; cities: string[] }) => void;
}) {
  const [countries, setCountries] = useState<RegionCountry[]>([]);
  const [detail, setDetail] = useState<RegionCountryDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.listCountries().then(setCountries).catch(() => setCountries([]));
  }, []);

  useEffect(() => {
    if (!country) {
      setDetail(null);
      return;
    }
    let stale = false;
    setLoading(true);
    api
      .getCountry(country)
      // A country with no region data (an older free-text value that isn't
      // one of the eight the connectors serve) leaves the tiers below closed
      // rather than erroring -- the country preference itself still works.
      .then((d) => !stale && setDetail(d))
      .catch(() => !stale && setDetail(null))
      .finally(() => !stale && setLoading(false));
    return () => {
      stale = true;
    };
  }, [country]);

  const subdivisionLabel = detail?.subdivision_label ?? "State";

  const stateOptions: CheckboxOption[] = useMemo(
    () =>
      (detail?.subdivisions ?? []).map((s) => ({
        value: s.code,
        label: s.label,
        count: s.job_count,
      })),
    [detail],
  );

  // Cities on offer: those in the selected states, or the whole country when
  // "all states" is selected.
  const cityOptions: CheckboxOption[] = useMemo(() => {
    if (!detail) return cities.map((c) => ({ value: c, label: c, custom: true }));
    const wanted = new Set(states);
    const offered = detail.subdivisions
      .filter((s) => wanted.size === 0 || wanted.has(s.code))
      .flatMap((s) => s.cities.map((c) => ({ value: c.name, label: c.name, count: c.job_count })));

    const known = new Set(offered.map((o) => o.value));
    const carried = cities
      .filter((c) => !known.has(c))
      .map((c) => ({ value: c, label: c, custom: true }));
    return [...carried, ...offered];
  }, [detail, states, cities]);

  const onCountryChange = (slug: string) => {
    // States and cities are both scoped to a country -- "WA" is Washington in
    // the US and Western Australia in Australia -- so changing it clears
    // them. The API enforces the same rule; doing it here too means the form
    // never shows a selection the server has already discarded.
    onChange({ country: slug, states: [], cities: [] });
  };

  const onStatesChange = (next: string[]) => {
    if (!detail) {
      onChange({ country, states: next, cities });
      return;
    }
    const wanted = new Set(next);
    const stillOffered = new Set(
      detail.subdivisions
        .filter((s) => wanted.size === 0 || wanted.has(s.code))
        .flatMap((s) => s.cities.map((c) => c.name)),
    );
    // A city the user typed in themselves has no state to belong to, so it
    // survives every state change rather than being pruned by one.
    const knownEverywhere = new Set(
      detail.subdivisions.flatMap((s) => s.cities.map((c) => c.name)),
    );
    onChange({
      country,
      states: next,
      cities: cities.filter((c) => stillOffered.has(c) || !knownEverywhere.has(c)),
    });
  };

  return (
    <>
      <div className="field">
        <label htmlFor="set-country">Country</label>
        <select id="set-country" value={country} onChange={(e) => onCountryChange(e.target.value)}>
          <option value="">Anywhere</option>
          {countries.map((c) => (
            <option key={c.slug} value={c.slug}>{c.label}</option>
          ))}
          {/* A value saved before this was a dropdown may not be one of the
              options; showing it keeps the form honest about what is stored. */}
          {country && !countries.some((c) => c.slug === country) && (
            <option value={country}>{country}</option>
          )}
        </select>
        <div className="field-hint">
          Postings elsewhere get flagged and scored down. Left on “Anywhere”, country is ignored.
        </div>
      </div>

      <CheckboxDropdown
        label={`${subdivisionLabel}s`}
        allLabel={`All ${subdivisionLabel.toLowerCase()}s`}
        options={stateOptions}
        selected={states}
        onChange={onStatesChange}
        searchPlaceholder={`Search ${subdivisionLabel.toLowerCase()}s…`}
        emptyText={loading ? "Loading…" : `No ${subdivisionLabel.toLowerCase()}s match that.`}
        disabled={!detail}
        hint={
          !country
            ? "Pick a country first."
            : !detail && !loading
              ? "No region data for that country, so this stays off."
              : states.length === 0
                ? `Every ${subdivisionLabel.toLowerCase()} is included. The number beside each is how many postings are there now.`
                : `Postings outside your ${states.length === 1 ? "selection" : "selections"} are flagged. A posting whose ${subdivisionLabel.toLowerCase()} can't be read from its location is left alone rather than hidden.`
        }
      />

      <CheckboxDropdown
        label="Cities"
        allLabel={states.length ? `All cities in those ${subdivisionLabel.toLowerCase()}s` : "All cities"}
        options={cityOptions}
        selected={cities}
        onChange={(next) => onChange({ country, states, cities: next })}
        searchPlaceholder="Search cities…"
        emptyText={loading ? "Loading…" : "No cities match that."}
        disabled={!detail && cityOptions.length === 0}
        hint={
          cities.length === 0
            ? "No cities set, so only the wider country and region settings apply."
            : "Jobs outside these are hidden. Remote roles are always shown."
        }
      />
    </>
  );
}
