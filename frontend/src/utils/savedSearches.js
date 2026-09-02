const SAVED_KEY = 'contract-scout:saved-searches'

function readSearches() {
  try {
    const raw = localStorage.getItem(SAVED_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function writeSearches(searches) {
  try {
    localStorage.setItem(SAVED_KEY, JSON.stringify(searches))
  } catch {
    // ignore storage errors
  }
}

function makeId() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

export function loadSavedSearches() {
  return readSearches()
}

export function addSavedSearch(searches, name, params) {
  const next = [
    ...searches,
    { id: makeId(), name, params, createdAt: Date.now() },
  ]
  writeSearches(next)
  return next
}

export function removeSavedSearch(searches, id) {
  const next = searches.filter((entry) => entry.id !== id)
  writeSearches(next)
  return next
}

export function renameSavedSearch(searches, id, name) {
  const next = searches.map((entry) => (entry.id === id ? { ...entry, name } : entry))
  writeSearches(next)
  return next
}
