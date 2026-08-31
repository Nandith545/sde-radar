import { useEffect, useState } from "react";
import * as api from "../api";
import type { PostalLookup, RegionCountry } from "../api";

/**
 * Fills in the city and state of the *profile address* from a postal code.
 *
 * Deliberately not a job filter. No connector returns a postal code and
 * JobListing has no column for one, so a postal-code job filter could only
 * ever match nothing; this writes into the address used on applications and
 * says as much.
 *
 * Only the three countries whose codes map to a subdivision cleanly are
 * offered. Being wrong about someone's own address is worse than asking them
 * to type it, so an unresolvable code says so rather than guessing.
 *
 * It appends to the address rather than rewriting it: a control that silently
 * overwrote a typed address would lose work with no way back.
 */
export default function PostalAutofill({
  preferredCountry,
  onAppend,
}: {
  /** The country already chosen for job matching. Used only to pick a
   * sensible starting option -- defaulting to whichever supported country
   * sorts first would offer Australia to someone who just said United
   * States. */
  preferredCountry: string;
  onAppend: (line: string) => void;
}) {
  const [countries, setCountries] = useState<RegionCountry[]>([]);
  const [country, setCountry] = useState("");
  // Whether the country here was chosen deliberately. Until it is, it tracks
  // the work-preference country -- which arrives after the first render, so
  // "only set it if it's still empty" would leave it stuck on whatever
  // sorted first.
  const [countryTouched, setCountryTouched] = useState(false);
  const [code, setCode] = useState("");
  const [result, setResult] = useState<PostalLookup | null>(null);
  const [city, setCity] = useState("");
  const [status, setStatus] = useState<"idle" | "looking" | "missed">("idle");

  useEffect(() => {
    api
      .listCountries()
      .then((all) => {
        const supported = all.filter((c) => c.supports_postal_lookup);
        setCountries(supported);
        const preferred = supported.some((c) => c.slug === preferredCountry)
          ? preferredCountry
          : supported[0]?.slug || "";
        setCountry((current) => (countryTouched ? current : preferred));
      })
      .catch(() => setCountries([]));
  }, [preferredCountry, countryTouched]);

  // Debounced: this fires per keystroke otherwise, and a half-typed code is
  // an unresolvable one, so the field would flash "couldn't place that" at
  // someone who is still typing.
  useEffect(() => {
    const trimmed = code.trim();
    if (!country || trimmed.length < 3) {
      setResult(null);
      setStatus("idle");
      return;
    }
    setStatus("looking");
    // `stale` belongs to the effect, not the timeout callback: a request
    // already in flight when the code changes must not land on top of the
    // newer one's answer, and a flag declared inside the callback could
    // never be set by the cleanup.
    let stale = false;
    const timer = setTimeout(() => {
      api
        .lookupPostal(country, trimmed)
        .then((found) => {
          if (stale) return;
          setResult(found);
          setCity(found?.cities[0] ?? "");
          setStatus(found ? "idle" : "missed");
        })
        .catch(() => !stale && setStatus("missed"));
    }, 350);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [country, code]);

  return (
    <div className="field postal-autofill">
      <label htmlFor="set-postal">Postal code</label>
      <div className="postal-row">
        <select
          aria-label="Postal code country"
          value={country}
          onChange={(e) => {
            setCountryTouched(true);
            setCountry(e.target.value);
          }}
        >
          {countries.map((c) => (
            <option key={c.slug} value={c.slug}>{c.label}</option>
          ))}
        </select>
        <input
          id="set-postal"
          value={code}
          autoComplete="postal-code"
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && e.preventDefault()}
          placeholder="e.g. 98052"
        />
      </div>

      {result && (
        <div className="postal-result">
          <strong>{result.label}</strong>
          <select aria-label="City" value={city} onChange={(e) => setCity(e.target.value)}>
            {result.cities.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <button
            type="button"
            className="btn secondary"
            onClick={() => onAppend(`${city}, ${result.code} ${code.trim()}`)}
          >
            Add to address
          </button>
        </div>
      )}

      <div className="field-hint">
        {status === "missed"
          ? `Couldn't place that code in ${countries.find((c) => c.slug === country)?.label ?? "that country"}.`
          : status === "looking"
            ? "Looking…"
            : "Fills the city and state on your address. It doesn't filter jobs — postings don't carry postal codes."}
      </div>
    </div>
  );
}
