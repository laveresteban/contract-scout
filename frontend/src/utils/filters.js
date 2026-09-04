export const DEFAULT_FILTER_VALUES = Object.freeze({
  query: 'software engineer',
  location: 'United States',
  job_type: 'contract',
  is_remote: true,
  employment_type: undefined,
  // Pay is compared as a yearly-USD equivalent; pay_unit remembers whether the
  // user typed an hourly rate or a yearly salary.
  min_yearly: undefined,
  max_yearly: undefined,
  pay_unit: 'hourly',
  source: undefined,
  company: undefined,
  sort_by: 'date_posted',
  sort_order: 'desc',
})

const RECENT_KEY = 'contract-scout:recent-searches'
const MAX_RECENT = 5

const FILTER_KEYS = [
  'query',
  'location',
  'job_type',
  'employment_type',
  'min_yearly',
  'max_yearly',
  'pay_unit',
  'source',
  'company',
  'sort_by',
  'sort_order',
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
    min_yearly: url.get('min_yearly') ? parseFloat(url.get('min_yearly')) : undefined,
    max_yearly: url.get('max_yearly') ? parseFloat(url.get('max_yearly')) : undefined,
    pay_unit: url.get('pay_unit') || DEFAULT_FILTER_VALUES.pay_unit,
    source: url.get('source') || undefined,
    company: url.get('company') || undefined,
    sort_by: url.get('sort_by') ?? DEFAULT_FILTER_VALUES.sort_by,
    sort_order: url.get('sort_order') ?? DEFAULT_FILTER_VALUES.sort_order,
    is_remote: true,
  }
}

const HOURS_PER_YEAR = 2080

// Show a pay filter back in the unit the user typed it in (hourly or yearly).
function payLabel(yearly, unit) {
  if (unit === 'hourly') return `$${Math.round(yearly / HOURS_PER_YEAR)}/hr`
  return `$${Math.round(yearly / 1000)}K/yr`
}

export function buildRecentLabel(params) {
  const filters = []
  if (params.employment_type) filters.push(params.employment_type.toUpperCase())
  if (params.min_yearly != null) filters.push(`min ${payLabel(params.min_yearly, params.pay_unit)}`)
  if (params.max_yearly != null) filters.push(`max ${payLabel(params.max_yearly, params.pay_unit)}`)
  if (params.source) filters.push(params.source)
  if (params.company) filters.push(params.company)
  const isDefaultSort =
    params.sort_by === DEFAULT_FILTER_VALUES.sort_by &&
    params.sort_order === DEFAULT_FILTER_VALUES.sort_order
  if (params.sort_by && !isDefaultSort) {
    filters.push(`sort: ${params.sort_by} ${params.sort_order}`)
  }
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
