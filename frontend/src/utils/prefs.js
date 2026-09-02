const FAVORITES_KEY = 'contract-scout:favorites'
const HIDDEN_KEY = 'contract-scout:hidden'
const LAST_VISIT_KEY = 'contract-scout:last-visit'

function readIds(key) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function writeIds(key, ids) {
  try {
    localStorage.setItem(key, JSON.stringify(ids))
  } catch {
    // ignore storage errors
  }
}

function toggleId(ids, id) {
  return ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]
}

export function loadFavorites() {
  return readIds(FAVORITES_KEY)
}

export function saveFavorites(ids) {
  writeIds(FAVORITES_KEY, ids)
}

export function toggleFavorite(ids, id) {
  const next = toggleId(ids, id)
  saveFavorites(next)
  return next
}

export function loadHidden() {
  return readIds(HIDDEN_KEY)
}

export function saveHidden(ids) {
  writeIds(HIDDEN_KEY, ids)
}

export function toggleHidden(ids, id) {
  const next = toggleId(ids, id)
  saveHidden(next)
  return next
}

export function clearHidden() {
  saveHidden([])
  return []
}

const THEME_KEY = 'contract-scout:theme'

export function loadTheme() {
  try {
    return localStorage.getItem(THEME_KEY) || 'light'
  } catch {
    return 'light'
  }
}

export function saveTheme(theme) {
  try {
    localStorage.setItem(THEME_KEY, theme)
  } catch {
    // ignore
  }
}

export function loadLastVisit() {
  try {
    const raw = localStorage.getItem(LAST_VISIT_KEY)
    return raw ? new Date(parseInt(raw, 10)) : null
  } catch {
    return null
  }
}

export function saveLastVisit(timestamp = Date.now()) {
  try {
    localStorage.setItem(LAST_VISIT_KEY, String(timestamp))
  } catch {
    // ignore
  }
}
