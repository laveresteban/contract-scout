export const DEFAULT_FILTER_VALUES = Object.freeze({
  query: 'software engineer',
  location: 'United States',
  job_type: 'contract',
  is_remote: true,
  employment_type: undefined,
  min_pay: undefined,
  max_pay: undefined,
  pay_interval: undefined,
  source: undefined,
})

const RECENT_KEY = 'contract-scout:recent-searches'
const MAX_RECENT = 5

const FILTER_KEYS = [
  'query',
  'location',
  'job_type',
  'employment_type',
  'min_pay',
  'max_pay',
  'pay_interval',
  'source',
]

function sameParams(a, b) {
  return FILTER_KEYS.every((key) => a[key] === b[key])
}

export function serializeFilters(params) {
  const url = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    if (key === 'is_remote') continue
    if (DEFAULT_FILTER_VALUES[key] !== undefined && value === DEFAULT_FILTER_VALUES[key]) continue
    url.set(key, String(value))
  }
  return url.toString()
}

export function deserializeFilters(search) {
  const url = new URLSearchParams(search)
  return {
    query: url.get('query') ?? DEFAULT_FILTER_VALUES.query,
    location: url.get('location') ?? DEFAULT_FILTER_VALUES.location,
    job_type: url.get('job_type') ?? DEFAULT_FILTER_VALUES.job_type,
    employment_type: url.get('employment_type') || undefined,
    min_pay: url.get('min_pay') ? parseFloat(url.get('min_pay')) : undefined,
    max_pay: url.get('max_pay') ? parseFloat(url.get('max_pay')) : undefined,
    pay_interval: url.get('pay_interval') || undefined,
    source: url.get('source') || undefined,
    is_remote: true,
  }
}

export function buildRecentLabel(params) {
  const filters = []
  if (params.employment_type) filters.push(params.employment_type.toUpperCase())
  if (params.min_pay != null) filters.push(`min $${params.min_pay}`)
  if (params.max_pay != null) filters.push(`max $${params.max_pay}`)
  if (params.pay_interval) filters.push(params.pay_interval)
  if (params.source) filters.push(params.source)
  const base = params.query || 'All jobs'
  if (!filters.length) return base
  return `${base} · ${filters.join(', ')}`
}

export function loadRecentSearches() {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

export function saveRecentSearches(recent) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(recent.slice(0, MAX_RECENT)))
  } catch {
    // ignore storage errors
  }
}

export function addRecentSearch(recent, params) {
  const label = buildRecentLabel(params)
  const entry = { params, label, timestamp: Date.now() }
  const next = [entry, ...recent.filter((r) => !sameParams(r.params, params))].slice(0, MAX_RECENT)
  saveRecentSearches(next)
  return next
}
