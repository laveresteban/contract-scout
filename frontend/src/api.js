const API_BASE = '/api/v1'
const TOKEN_KEY = 'contract-scout:token'

let authToken = null
try {
  authToken = localStorage.getItem(TOKEN_KEY)
} catch {
  authToken = null
}

export function setToken(token) {
  authToken = token || null
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // ignore storage errors
  }
}

export function getToken() {
  return authToken
}

function authHeaders(extra = {}) {
  const headers = { ...extra }
  if (authToken) headers.Authorization = `Bearer ${authToken}`
  return headers
}

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: authHeaders(options.headers),
  })
  if (!res.ok) throw new Error(await res.text())
  const contentType = res.headers.get('content-type') || ''
  return contentType.includes('application/json') ? res.json() : res.text()
}

export async function listSources() {
  return request('/sources')
}

export async function scrapeJobs(params) {
  return request('/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
}

export async function listJobs(params) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.append(key, value)
    }
  })
  const res = await fetch(`${API_BASE}/jobs?${query.toString()}`, { headers: authHeaders() })
  if (!res.ok) throw new Error(await res.text())
  const jobs = await res.json()
  const total = parseInt(res.headers.get('X-Total-Count') || '', 10)
  return { jobs, total: Number.isNaN(total) ? jobs.length : total }
}

// Short-list guardrail: how many query matches the default remote+US filters
// hide. Params mirror listJobs (minus is_remote/is_us, which the endpoint owns).
export async function getHiddenCount(params) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.append(key, value)
  })
  return request(`/jobs/hidden-count?${query.toString()}`)
}

export async function getJob(id) {
  return request(`/jobs/${encodeURIComponent(id)}`)
}

export async function getJobStats() {
  return request('/jobs/stats')
}

// Re-fetch the original posting to confirm it's still live. `force` bypasses
// the backend's freshness cache for a manual re-check.
export async function verifyJob(id, { force = false } = {}) {
  return request(`/jobs/${encodeURIComponent(id)}/verify${force ? '?force=true' : ''}`, {
    method: 'POST',
  })
}

export async function verifyJobs(ids) {
  return request('/jobs/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  })
}

export async function getScrapeHealth() {
  return request('/scrape/health')
}

// --- Auth -------------------------------------------------------------------
export async function listAuthProviders() {
  return request('/auth/providers')
}

export async function getCurrentUser() {
  return request('/auth/me')
}

export function loginUrl(provider) {
  return `${API_BASE}/auth/${provider}/login`
}

// --- Server-backed prefs ----------------------------------------------------
export const prefsApi = {
  listSaved: () => request('/prefs/saved-jobs'),
  addSaved: (id) => request(`/prefs/saved-jobs/${encodeURIComponent(id)}`, { method: 'PUT' }),
  removeSaved: (id) => request(`/prefs/saved-jobs/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  listHidden: () => request('/prefs/hidden-jobs'),
  addHidden: (id) => request(`/prefs/hidden-jobs/${encodeURIComponent(id)}`, { method: 'PUT' }),
  removeHidden: (id) => request(`/prefs/hidden-jobs/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  clearHidden: () => request('/prefs/hidden-jobs', { method: 'DELETE' }),
  listViewed: () => request('/prefs/viewed-jobs'),
  markViewed: (id) => request(`/prefs/viewed-jobs/${encodeURIComponent(id)}`, { method: 'PUT' }),
}

// --- Server-backed saved searches ------------------------------------------
export const savedSearchApi = {
  list: () => request('/prefs/saved-searches'),
  create: (payload) =>
    request('/prefs/saved-searches', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  update: (id, payload) =>
    request(`/prefs/saved-searches/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  remove: (id) => request(`/prefs/saved-searches/${id}`, { method: 'DELETE' }),
}
