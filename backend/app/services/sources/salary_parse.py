"""Best-effort extraction of a min/max compensation figure from free-text
salary strings, for connectors that don't return structured salary fields.
"""
import re

_RANGE = re.compile(
    r"\$?\s*([\d,]+(?:\.\d+)?)\s*[kK]?\s*(?:-|to|–)\s*\$?\s*([\d,]+(?:\.\d+)?)\s*[kK]?", re.IGNORECASE
)
_SINGLE = re.compile(r"\$?\s*([\d,]+(?:\.\d+)?)\s*[kK]?")
_HOURLY_HINT = re.compile(r"\bhour|/hr\b", re.IGNORECASE)
_K_HINT = re.compile(r"\d[kK]\b")


def _to_number(raw: str, treat_as_thousands: bool) -> float:
    n = float(raw.replace(",", ""))
    return n * 1000 if treat_as_thousands else n


def parse_salary_text(text: str) -> tuple[float | None, float | None, str]:
    """Returns (comp_min, comp_max, comp_unit). comp_unit is 'hour' if the
    text mentions an hourly rate, otherwise 'year'. Returns (None, None,
    'year') if nothing plausible is found.
    """
    if not text:
        return None, None, "year"
    unit = "hour" if _HOURLY_HINT.search(text) else "year"
    thousands = bool(_K_HINT.search(text))

    range_match = _RANGE.search(text)
    if range_match:
        try:
            lo = _to_number(range_match.group(1), thousands)
            hi = _to_number(range_match.group(2), thousands)
            if lo > hi:
                lo, hi = hi, lo
            return lo, hi, unit
        except ValueError:
            pass

    single_match = _SINGLE.search(text)
    if single_match:
        try:
            val = _to_number(single_match.group(1), thousands)
            return val, val, unit
        except ValueError:
            pass

    return None, None, "year"
