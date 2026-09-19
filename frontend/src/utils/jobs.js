function normalize(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/&amp;/g, 'and')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

// Company names vary across boards ("Acme", "Acme, Inc.", "Acme LLC"). Strip
// common legal suffixes and punctuation so the same employer collapses to one
// identity.
const COMPANY_SUFFIX_RE =
  /\b(inc|incorporated|llc|l l c|ltd|limited|corp|corporation|co|company|gmbh|plc|group|holdings|technologies|technology|labs|inc\.?)\b/g

function normalizeCompany(value) {
  return normalize(value).replace(COMPANY_SUFFIX_RE, ' ').replace(/\s+/g, ' ').trim()
}

// Remote roles list location inconsistently ("Remote", "United States",
// "Remote, US", "Anywhere"). Collapse all of these to a single bucket so they
// don't split an otherwise-identical posting into duplicates, while keeping a
// real city/state distinct.
const REMOTE_LOCATION_RE =
  /^(remote|anywhere|us|usa|united states|remote us|us remote|remote united states|nationwide|work from home|wfh)$/

function normalizeLocation(value) {
  const normalized = normalize(value)
  if (!normalized || REMOTE_LOCATION_RE.test(normalized)) return ''
  return normalized
}

// Titles pick up decorations that don't change the role: "(Remote)",
// "- Contract", trailing "W2/C2C", req numbers. Strip parentheticals/brackets
// and a few engagement qualifiers so variants of one posting collapse.
const TITLE_NOISE_RE =
  /\b(remote|hybrid|onsite|on site|contract|contractor|w2|c2c|1099|full time|part time|urgent|hiring|immediate)\b/g

function normalizeTitle(value) {
  return normalize(String(value || '').replace(/[([{].*?[)\]}]/g, ' '))
    .replace(TITLE_NOISE_RE, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function canonicalUrl(value) {
  if (!value) return ''
  try {
    const url = new URL(value)
    url.hash = ''
    ;[...url.searchParams.keys()]
      .filter((key) => /^(utm_|source|ref|trk|tracking)/i.test(key))
      .forEach((key) => url.searchParams.delete(key))
    return url.toString().replace(/\/$/, '').toLowerCase()
  } catch {
    return String(value).trim().toLowerCase().replace(/\/$/, '')
  }
}

// Sources often publish the same role with different tracking URLs, so the
// normalized posting identity is preferred when the source has enough fields.
// The identity is title + company (+ a real location only when it's not a
// generic "remote" bucket), which merges the same role across boards.
export function jobDeduplicationKey(job) {
  const title = normalizeTitle(job.title)
  const company = normalizeCompany(job.company)
  if (title && company) {
    const location = normalizeLocation(job.location)
    return `posting:${title}|${company}${location ? `|${location}` : ''}`
  }

  const url = canonicalUrl(job.job_url_direct || job.job_url)
  return url ? `url:${url}` : `id:${job.id}`
}

export function dedupeJobs(jobs) {
  const seen = new Set()
  return jobs.filter((job) => {
    const key = jobDeduplicationKey(job)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

export function mergeUniqueJobs(existing, incoming) {
  return dedupeJobs([...existing, ...incoming])
}
