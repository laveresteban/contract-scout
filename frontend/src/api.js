const API_BASE = '/api/v1'

export async function scrapeJobs(params) {
  const res = await fetch(`${API_BASE}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function listJobs(params) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.append(key, value)
    }
  })
  const res = await fetch(`${API_BASE}/jobs?${query.toString()}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}
