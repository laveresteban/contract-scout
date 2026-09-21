"""Shared posting-identity key, mirroring backend ``app/dedup.py`` and frontend
``utils/jobs.js``. Used by both the API spec and the Selenium UI spec so they
agree on what "the same job" means.
"""

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_STRIP = re.compile(r"[^a-z0-9]+")
_WS = re.compile(r"\s+")
_COMPANY_SUFFIX = re.compile(
    r"\b(inc|incorporated|llc|l l c|ltd|limited|corp|corporation|co|company|"
    r"gmbh|plc|group|holdings|technologies|technology|labs|solutions)\b"
)
_TITLE_NOISE = re.compile(
    r"\b(remote|hybrid|onsite|on site|contract|contractor|w2|c2c|1099|"
    r"full time|part time|urgent|hiring|immediate)\b"
)
_REMOTE_LOCATION = re.compile(
    r"^(remote|anywhere|us|usa|united states|remote us|us remote|"
    r"remote united states|nationwide|work from home|wfh)$"
)
_TRACKING = re.compile(r"^(utm_|source|ref|trk|tracking)", re.IGNORECASE)


def _norm(value):
    text = (value or "").lower().replace("&amp;", "and")
    return _WS.sub(" ", _STRIP.sub(" ", text)).strip()


def normalize_company(value):
    return _WS.sub(" ", _COMPANY_SUFFIX.sub(" ", _norm(value))).strip()


def normalize_title(value):
    without_brackets = re.sub(r"[([{].*?[)\]}]", " ", value or "")
    return _WS.sub(" ", _TITLE_NOISE.sub(" ", _norm(without_brackets))).strip()


def normalize_location(value):
    n = _norm(value)
    return "" if not n or _REMOTE_LOCATION.match(n) else n


def _canonical_url(value):
    if not value:
        return ""
    try:
        p = urlparse(value)
        q = [(k, v) for k, v in parse_qsl(p.query) if not _TRACKING.match(k)]
        return urlunparse(p._replace(fragment="", query=urlencode(q))).rstrip("/").lower()
    except ValueError:
        return value.strip().rstrip("/").lower()


def dedup_key(*, title=None, company=None, location=None, url=None, job_id=None):
    t, c = normalize_title(title), normalize_company(company)
    if t and c:
        loc = normalize_location(location)
        return "posting:{}|{}{}".format(t, c, "|" + loc if loc else "")
    canon = _canonical_url(url)
    return "url:" + canon if canon else "id:" + str(job_id)
