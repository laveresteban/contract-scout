from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Compensation:
    minimum: float | None = None
    maximum: float | None = None
    currency: str | None = None
    interval: str | None = None
    source: str | None = None
    confidence: str | None = None
    raw_text: str | None = None


_INTERVALS = {
    "hour": "hourly",
    "hr": "hourly",
    "hourly": "hourly",
    "day": "daily",
    "daily": "daily",
    "week": "weekly",
    "wk": "weekly",
    "weekly": "weekly",
    "month": "monthly",
    "mo": "monthly",
    "monthly": "monthly",
    "year": "yearly",
    "yr": "yearly",
    "yearly": "yearly",
    "annual": "yearly",
    "annually": "yearly",
    "annum": "yearly",
}
_INTERVAL_TOKEN = r"(?:hours?|hrs?|hourly|days?|daily|weeks?|wks?|weekly|months?|monthly|years?|yrs?|yearly|annual(?:ly)?|annum)"
_CONTEXT = r"(?:base\s+)?(?:pay|rate|compensation|salary|wage)(?:\s+range)?\s*(?:is|of|:)?\s*"


def normalize_interval(value: str | None) -> str | None:
    raw = re.sub(r"[_-]+", " ", (value or "").lower()).strip()
    for token, normalized in _INTERVALS.items():
        if re.search(rf"\b{re.escape(token)}s?\b", raw):
            return normalized
    return None


def _number(value: Any, suffix: str = "") -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    return number * 1000 if suffix.lower() == "k" else number


def _clean(text: str | None) -> str:
    value = html.unescape(re.sub(r"<[^>]*>", " ", text or ""))
    value = re.sub(r"\\(?=[$\-–—])", "", value)
    value = re.sub(r"[*`]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _currency(text: str) -> str | None:
    match = re.search(r"\b(USD|CAD|EUR|GBP|AUD|INR|MXN|BRL)\b", text, re.I)
    if match:
        return match.group(1).upper()
    if "$" in text:
        return "USD"
    return None


def _interval(value: str) -> str | None:
    return normalize_interval(value)


def parse_compensation_text(text: str | None) -> Compensation:
    cleaned = _clean(text)
    if not cleaned:
        return Compensation()
    number = r"\d+(?:,\d{3})*(?:\.\d+)?"
    amount_min = rf"(?:USD\s*)?\$?\s*(?P<minimum>{number})(?P<minimum_k>[kK]?)"
    amount_max = rf"(?:USD\s*)?\$?\s*(?P<maximum>{number})(?P<maximum_k>[kK]?)"
    amount = rf"(?:USD\s*)?\$?\s*(?P<amount>{number})(?P<amount_k>[kK]?)"

    match = re.search(
        rf"(?P<context>{_CONTEXT})?{amount_min}\s*(?:-|–|—|to)\s*{amount_max}\s*(?:/|per\s+|an?\s+)?(?P<unit>{_INTERVAL_TOKEN})",
        cleaned,
        re.I,
    )
    if match and (match.group("context") or _currency(match.group(0))):
        raw = match.group(0)
        return Compensation(_number(match.group("minimum"), match.group("minimum_k")), _number(match.group("maximum"), match.group("maximum_k")), _currency(raw), _interval(match.group("unit")), "description", "high" if match.group("context") else "medium", raw)

    match = re.search(
        rf"(?P<context>{_CONTEXT}){amount_min}\s*(?:-|–|—|to|and)\s*{amount_max}(?:\s*(?:/|per\s+|an?\s+)?(?P<unit>{_INTERVAL_TOKEN}))?",
        cleaned,
        re.I,
    )
    if match:
        raw = match.group(0)
        interval = _interval(match.group("unit") or "") or "yearly"
        return Compensation(_number(match.group("minimum"), match.group("minimum_k")), _number(match.group("maximum"), match.group("maximum_k")), _currency(raw), interval, "description", "high", raw)

    match = re.search(
        rf"(?P<bound>up\s+to|maximum(?:\s+of)?|from|starting(?:\s+at)?|minimum(?:\s+of)?)\s*{amount}\s*(?:/|per\s+|an?\s+)?(?P<unit>{_INTERVAL_TOKEN})",
        cleaned,
        re.I,
    )
    if match:
        value = _number(match.group("amount"), match.group("amount_k"))
        lower_bound = match.group("bound").lower().startswith(("from", "starting", "minimum"))
        raw = match.group(0)
        return Compensation(value if lower_bound else None, None if lower_bound else value, _currency(raw), _interval(match.group("unit")), "description", "high", raw)

    match = re.search(
        rf"(?P<context>{_CONTEXT})?{amount}\s*(?:/|per\s+|an?\s+)?(?P<unit>{_INTERVAL_TOKEN})",
        cleaned,
        re.I,
    )
    if match and (match.group("context") or _currency(match.group(0))):
        value = _number(match.group("amount"), match.group("amount_k"))
        raw = match.group(0)
        return Compensation(value, value, _currency(raw), _interval(match.group("unit")), "description", "high" if match.group("context") else "medium", raw)

    return Compensation()


def extract_compensation(
    text: str | None = None,
    *,
    minimum: Any = None,
    maximum: Any = None,
    currency: str | None = None,
    interval: str | None = None,
) -> Compensation:
    structured_min = _number(minimum)
    structured_max = _number(maximum)
    parsed = parse_compensation_text(text)
    if structured_min is None and structured_max is None:
        return parsed
    normalized_interval = normalize_interval(interval) or parsed.interval
    normalized_currency = (currency or parsed.currency or "").upper() or None
    raw = parsed.raw_text
    return Compensation(
        structured_min if structured_min is not None else parsed.minimum,
        structured_max if structured_max is not None else parsed.maximum,
        normalized_currency,
        normalized_interval,
        "structured",
        "high" if normalized_interval else "medium",
        raw,
    )


_FALSE_CONTRACT_CONTEXTS = [
    re.compile(r"\bcontingent\s+(?:upon|on)\s+(?:a\s+)?contract\s+award\b", re.I),
    re.compile(r"\b(?:federal|government|customer|client|prime)\s+contracts?\b", re.I),
    re.compile(r"\bcontracts?\s+(?:requirements?|policy|funding|vehicle|allows?)\b", re.I),
    re.compile(r"\bcontractual\s+requirements?\b", re.I),
    re.compile(r"\bcomply-to-connect\s*\(?(?:c2c)?\)?", re.I),
]
_NEGATED_ENGAGEMENT = re.compile(
    r"\b(?:(?:no|not\s+open\s+to|do\s+not\s+accept|unable\s+to\s+accept|refrain\s+from\s+applying)[^.\n]{0,100}(?:c2c|corp(?:oration)?[- 2to]+corp(?:oration)?|1099|contractors?)|(?:c2c|corp(?:oration)?[- 2to]+corp(?:oration)?|1099|contractors?)[^.\n]{0,100}(?:refrain\s+from\s+applying|need\s+not\s+apply|not\s+accepted))\b",
    re.I,
)
_W2_SIGNAL = re.compile(r"\b(?:direct[- ]hire|w-?2\s+(?:only|position|role|employee|contract)|full[- ]time\s+employee)\b", re.I)
_CONTRACT_SIGNALS = [
    re.compile(r"\bcontractors?\b", re.I),
    re.compile(r"\bcontract(?:ual)?\s+(?:role|position|opportunity|job|employment|engagement)\b", re.I),
    re.compile(r"\bcontract[- ]to[- ]hire\b", re.I),
    re.compile(r"\b(?:\d+|three|six|twelve)[- ]?(?:week|month|year)s?\s+(?:contract|assignment|engagement)\b", re.I),
    re.compile(r"\btemporary\s+(?:role|position|assignment|contract|engagement)\b", re.I),
    re.compile(r"\bconsult(?:ing|ant)\s+(?:role|position|assignment|contract|engagement)\b", re.I),
    re.compile(r"\bindependent\s+contractors?\b", re.I),
    re.compile(r"\bfreelanc(?:e|er)s?\b", re.I),
    re.compile(r"\b1099\b", re.I),
    re.compile(r"\b(?:c2c|corp[- ]to[- ]corp|corp[- ]2[- ]corp)\b", re.I),
]


def contract_role_signal(text: str | None) -> bool:
    cleaned = _clean(text).lower()
    if not cleaned:
        return False
    cleaned = _NEGATED_ENGAGEMENT.sub(" ", cleaned)
    for pattern in _FALSE_CONTRACT_CONTEXTS:
        cleaned = pattern.sub(" ", cleaned)
    return any(pattern.search(cleaned) for pattern in _CONTRACT_SIGNALS)


def job_type_signal(description: str | None, title: str | None = None) -> tuple[str | None, str | None, str | None]:
    text = _clean(" ".join(filter(None, (title, description))))
    if contract_role_signal(text):
        return "contract", "contract_text", "medium"
    if re.search(r"\b(?:job|employment|position|requisition)\s+type\s*:?\s*(?:regular|full[- ]?time)\b|\bdirect[- ]hire\b|\bpermanent\s+(?:employee|role|position)\b|\bfull[- ]?time\s+(?:employee|role|position)\b", text, re.I):
        return "fulltime", "explicit_employee", "high"
    return None, None, None


def employment_type_signal(description: str | None, title: str | None = None) -> tuple[str | None, str | None, str | None]:
    text = _clean(" ".join(filter(None, (title, description))))
    masked = text
    for pattern in _FALSE_CONTRACT_CONTEXTS:
        masked = pattern.sub(" ", masked)
    if _NEGATED_ENGAGEMENT.search(text) or _W2_SIGNAL.search(text):
        return "w2", "explicit_w2", "high"
    if re.search(r"\b(?:c2c|corp[- ]to[- ]corp|corp[- ]2[- ]corp)\b", masked, re.I):
        return "c2c", "explicit_c2c", "high"
    if re.search(r"\b1099\b|\bindependent\s+contractors?\b", masked, re.I):
        return "1099", "explicit_1099", "high"
    if re.search(r"\bw-?2\b|\bfull[- ]time\s+employee\b|\bemployee\s+position\b", masked, re.I):
        return "w2", "explicit_w2", "high"
    if contract_role_signal(masked):
        return "contract", "contract_text", "medium"
    return None, None, None
