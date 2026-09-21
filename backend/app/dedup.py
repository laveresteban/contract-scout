"""Single source of truth for cross-source job de-duplication.

Both ingest paths -- ``services.persist.save_jobs`` (the ``/search`` scrape) and
``services.scan._ingest_job`` (saved-search background scans) -- MUST derive a
job's dedup key from this module so a role scraped by one path collapses onto the
same row as the identical role scraped by the other. It deliberately mirrors the
frontend's ``src/utils/jobs.js`` grouping (title + company, plus a real location
only when it isn't a generic "remote" bucket) so the client-side dedup that the
UI still runs as a safety net becomes a no-op instead of silently shortening each
page.

The stored ``Job.dedup_key`` is an opaque hash of that identity; nothing compares
it to the frontend's string key, so the hash form is free to differ -- only the
*grouping* has to match, which the shared normalization guarantees.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

_STRIP = re.compile(r"[^a-z0-9]+")
_WS = re.compile(r"\s+")

# Legal-suffix / boilerplate words that don't change employer identity.
_COMPANY_SUFFIX = re.compile(
    r"\b(inc|incorporated|llc|l l c|ltd|limited|corp|corporation|co|company|"
    r"gmbh|plc|group|holdings|technologies|technology|labs|solutions)\b"
)

# Title decorations that don't change the role.
_TITLE_NOISE = re.compile(
    r"\b(remote|hybrid|onsite|on site|contract|contractor|w2|c2c|1099|"
    r"full time|part time|urgent|hiring|immediate)\b"
)

# Generic "this is a remote/US posting" location buckets that must not split an
# otherwise-identical posting into distinct rows.
_REMOTE_LOCATION = re.compile(
    r"^(remote|anywhere|us|usa|united states|remote us|us remote|"
    r"remote united states|nationwide|work from home|wfh)$"
)

# Tracking query params dropped when a URL is the fallback identity.
_TRACKING_PARAM = re.compile(r"^(utm_|source|ref|trk|tracking)", re.IGNORECASE)


def _normalize(value: str | None) -> str:
    text = str(value or "").lower().replace("&amp;", "and")
    return _WS.sub(" ", _STRIP.sub(" ", text)).strip()


def normalize_company(value: str | None) -> str:
    return _WS.sub(" ", _COMPANY_SUFFIX.sub(" ", _normalize(value))).strip()


def normalize_title(value: str | None) -> str:
    # Drop bracketed/parenthesized decorations before word-level cleanup.
    without_brackets = re.sub(r"[([{].*?[)\]}]", " ", str(value or ""))
    return _WS.sub(" ", _TITLE_NOISE.sub(" ", _normalize(without_brackets))).strip()


def normalize_location(value: str | None) -> str:
    normalized = _normalize(value)
    if not normalized or _REMOTE_LOCATION.match(normalized):
        return ""
    return normalized


def canonical_url(value: str | None) -> str:
    if not value:
        return ""
    try:
        parts = urlparse(value)
        query = [(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING_PARAM.match(k)]
        rebuilt = urlunparse(parts._replace(fragment="", query=urlencode(query)))
        return rebuilt.rstrip("/").lower()
    except ValueError:
        return str(value).strip().rstrip("/").lower()


def dedup_key(
    *,
    company: str | None,
    title: str | None,
    location: str | None = None,
    url: str | None = None,
    job_id: str | None = None,
) -> str:
    """Return the opaque cross-source identity for a posting.

    Tiered exactly like the frontend: prefer the normalized title + company
    (+ a real, non-generic location), else a canonicalized URL, else the raw id.
    """
    ntitle = normalize_title(title)
    ncompany = normalize_company(company)
    if ntitle and ncompany:
        nloc = normalize_location(location)
        raw = f"posting:{ntitle}|{ncompany}" + (f"|{nloc}" if nloc else "")
    else:
        canon = canonical_url(url)
        raw = f"url:{canon}" if canon else f"id:{job_id or ''}"
    return hashlib.md5(raw.encode()).hexdigest()[:24]
