"""Helpers for pay normalization and location/eligibility classification.

These are pure functions so they can be reused by the API layer, the Pydantic
models (as computed fields), and the alert matcher.
"""
from __future__ import annotations

import re

from app.config import FX_RATES, HOURS_PER_YEAR, MONTHS_PER_YEAR


def _interval_multiplier(interval: str | None) -> float | None:
    """Return the factor to convert a per-`interval` amount to a yearly amount."""
    if not interval:
        return None
    i = interval.lower()
    if "hour" in i or i in ("hr", "hourly"):
        return float(HOURS_PER_YEAR)
    if "month" in i or i == "monthly":
        return float(MONTHS_PER_YEAR)
    if "week" in i or i == "weekly":
        return 52.0
    if "day" in i or i == "daily":
        return 260.0
    if "year" in i or i in ("yr", "yearly", "annually"):
        return 1.0
    return None


def normalize_amount(amount: float | None, interval: str | None, currency: str | None) -> float | None:
    """Convert an amount to an approximate yearly USD figure.

    Returns None when we cannot confidently normalize (unknown interval or
    unknown currency). Currency defaults to USD when not provided.
    """
    if amount is None:
        return None
    multiplier = _interval_multiplier(interval)
    if multiplier is None:
        return None
    cur = (currency or "USD").upper()
    rate = FX_RATES.get(cur)
    if rate is None:
        return None
    return round(amount * multiplier * rate, 2)


def classify_eligibility(location: str | None, is_remote: bool, is_us: bool) -> str:
    """Classify how confident we are that a job is US-eligible.

    Returns one of: "explicit_us", "remote_us_assumed", "non_us", "unknown".
    """
    loc = (location or "").lower()
    explicit_us = bool(
        re.search(r"\bunited states\b|\busa?\b|\bu\.s\.a?\b", loc)
        or re.search(r"\bremote[- ]?(?:us|usa)\b", loc)
    )
    non_us = bool(
        re.search(
            r"\bindia\b|\bchina\b|\beurope\b|\buk\b|\bcanada\b|\bmexico\b|"
            r"\bbrazil\b|\bargentina\b|\bapac\b|\blatam\b|\baustralia\b|\basia\b|\bafrica\b",
            loc,
        )
    )
    if explicit_us:
        return "explicit_us"
    if non_us and not is_us:
        return "non_us"
    if is_us and is_remote:
        return "remote_us_assumed"
    if is_us:
        return "explicit_us"
    return "unknown"


ELIGIBILITY_LABELS = {
    "explicit_us": "US listed",
    "remote_us_assumed": "Remote (US assumed)",
    "non_us": "Non-US",
    "unknown": "Unknown",
}
