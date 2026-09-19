"""Extract compensation from a job posting's live page.

Boards frequently bury the pay in the body copy ("$95–$120 / hr", "$150,000 a
year") rather than in a structured field, so the scrape we started with often
has empty salary columns. When `verify` re-fetches the source we already hold
the page text — this module mines a pay range out of it and normalizes every
interval onto one yearly-USD scale so hourly contracts and salaried roles sort
together.

Everything here is best-effort and conservative: if we can't find a confident
range we return ``None`` and leave whatever the original scrape captured intact.
"""

import re

# Hours/periods per year used to project any interval onto a yearly figure.
# 2080 = 40h * 52wk is the standard full-time year; 260 = 52wk * 5 working days.
_PERIODS_PER_YEAR = {
    "hourly": 2080,
    "daily": 260,
    "weekly": 52,
    "monthly": 12,
    "yearly": 1,
}

# Map the many ways a board writes an interval onto our canonical keys.
_INTERVAL_WORDS = [
    (re.compile(r"\b(?:per\s+hour|/\s*h(?:ou)?r\b|an?\s+hour|hourly|/hr\b)", re.I), "hourly"),
    (re.compile(r"\b(?:per\s+day|/\s*day|a\s+day|daily|/day)", re.I), "daily"),
    (re.compile(r"\b(?:per\s+week|/\s*w(?:ee)?k|a\s+week|weekly|/wk)", re.I), "weekly"),
    (re.compile(r"\b(?:per\s+month|/\s*mo(?:nth)?|a\s+month|monthly|/mo)", re.I), "monthly"),
    (re.compile(r"\b(?:per\s+(?:year|annum|yr)|/\s*y(?:ea)?r|a\s+year|annually|yearly|p\.?a\.?)", re.I), "yearly"),
]

# A currency amount: optional symbol/code, digits with thousands separators, an
# optional decimal, and an optional K/M shorthand ($120k, $1.2M).
_AMOUNT = r"(?:USD\s*|US\$\s*|\$\s*)?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*([kKmM])?"

# A range ("$95 - $120", "95k to 120k") or a single amount, captured together
# with the trailing ~40 chars so we can read the interval that follows it.
_RANGE = re.compile(
    rf"{_AMOUNT}\s*(?:-|–|—|to)\s*{_AMOUNT}(?P<tail1>.{{0,40}})",
    re.I,
)
_SINGLE = re.compile(rf"{_AMOUNT}(?P<tail2>.{{0,40}})", re.I)

# Only treat "$…" text as pay when the surrounding copy is actually about money.
_PAY_CONTEXT = re.compile(
    r"\b(salar(?:y|ies|ied)|compensation|pays?|paid|rates?|/\s*hr|per\s+hour"
    r"|per\s+year|annum|annually|base|comp)\b",
    re.I,
)


def _to_number(digits: str, suffix: str | None) -> float:
    value = float(digits.replace(",", ""))
    if suffix:
        value *= 1_000_000 if suffix.lower() == "m" else 1_000
    return value


def _interval_from(text: str) -> str | None:
    for pattern, interval in _INTERVAL_WORDS:
        if pattern.search(text):
            return interval
    return None


def _guess_interval(amount: float) -> str:
    # No explicit unit: small numbers read as hourly rates, large ones as yearly.
    return "hourly" if amount < 2000 else "yearly"


def normalize_yearly(minimum: float | None, maximum: float | None, interval: str | None) -> tuple[float | None, float | None]:
    """Project a raw pay range onto yearly USD. Unknown interval → passthrough."""
    factor = _PERIODS_PER_YEAR.get(interval or "", None)
    if factor is None:
        return None, None
    norm_min = round(minimum * factor) if minimum is not None else None
    norm_max = round(maximum * factor) if maximum is not None else None
    return norm_min, norm_max


def parse_salary(text: str) -> dict | None:
    """Pull a compensation range out of free text.

    Returns a dict with ``min_amount``, ``max_amount``, ``currency``,
    ``interval`` and the normalized yearly figures, or ``None`` when nothing
    trustworthy is found.
    """
    if not text:
        return None
    # Collapse whitespace so ranges split across markup/newlines still match.
    text = re.sub(r"\s+", " ", text)
    if not _PAY_CONTEXT.search(text):
        return None

    minimum = maximum = None
    tail = ""

    match = _RANGE.search(text)
    if match:
        low = _to_number(match.group(1), match.group(2))
        high = _to_number(match.group(3), match.group(4))
        minimum, maximum = min(low, high), max(low, high)
        tail = match.group("tail1") or ""
    else:
        # Fall back to a single amount, but only in an unambiguous pay context.
        single = _SINGLE.search(text)
        if not single:
            return None
        minimum = maximum = _to_number(single.group(1), single.group(2))
        tail = single.group("tail2") or ""

    if minimum <= 0:
        return None

    # Read the interval from the text right after the amount, then widen to the
    # whole snippet, then fall back to a magnitude-based guess.
    interval = _interval_from(tail) or _interval_from(text) or _guess_interval(maximum)
    norm_min, norm_max = normalize_yearly(minimum, maximum, interval)

    # A sanity gate: yearly-equivalent below $10k or above $2M is almost
    # certainly a misparse (a phone number, a headcount, "$401k plan").
    ceiling = norm_max if norm_max is not None else norm_min
    if ceiling is not None and (ceiling < 10_000 or ceiling > 2_000_000):
        return None

    return {
        "min_amount": minimum,
        "max_amount": maximum,
        "currency": "USD",
        "interval": interval,
        "normalized_min_yearly": norm_min,
        "normalized_max_yearly": norm_max,
    }
