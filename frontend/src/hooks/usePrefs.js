import { useEffect, useState } from 'react'
import { prefsApi } from '../api'
import {
  addViewed,
  clearHidden as lsClearHidden,
  loadFavorites,
  loadHidden,
  loadViewed,
  toggleFavorite as lsToggleFavorite,
  toggleHidden as lsToggleHidden,
} from '../utils/prefs'

/**
 * Manage saved / hidden / viewed jobs, backed by the server when the user is
 * authenticated and by localStorage otherwise. The public API is identical in
 * both modes so callers don't need to branch.
 */
export function usePrefs(user) {
  const authed = Boolean(user)
  const [favorites, setFavorites] = useState(() => loadFavorites())
  const [hidden, setHidden] = useState(() => loadHidden())
  const [viewed, setViewed] = useState(() => loadViewed())

  useEffect(() => {
    if (!authed) {
      setFavorites(loadFavorites())
      setHidden(loadHidden())
      setViewed(loadViewed())
      return
    }
    let cancelled = false
    Promise.all([prefsApi.listSaved(), prefsApi.listHidden(), prefsApi.listViewed()])
      .then(([saved, hiddenIds, viewedIds]) => {
        if (cancelled) return
        setFavorites(saved)
        setHidden(hiddenIds)
        setViewed(viewedIds)
      })
      .catch(() => {
        /* keep whatever we have */
      })
    return () => {
      cancelled = true
    }
  }, [authed])

  const toggleFavorite = (id) => {
    const removing = favorites.includes(id)
    if (authed) {
      setFavorites((prev) => (removing ? prev.filter((x) => x !== id) : [...prev, id]))
      ;(removing ? prefsApi.removeSaved(id) : prefsApi.addSaved(id)).catch(() => {})
    } else {
      setFavorites((prev) => lsToggleFavorite(prev, id))
    }
    return removing
  }

  const toggleHidden = (id) => {
    const removing = hidden.includes(id)
    if (authed) {
      setHidden((prev) => (removing ? prev.filter((x) => x !== id) : [...prev, id]))
      ;(removing ? prefsApi.removeHidden(id) : prefsApi.addHidden(id)).catch(() => {})
    } else {
      setHidden((prev) => lsToggleHidden(prev, id))
    }
    return removing
  }

  const clearHidden = () => {
    if (authed) {
      setHidden([])
      prefsApi.clearHidden().catch(() => {})
    } else {
      setHidden(lsClearHidden())
    }
  }

  const markViewed = (id) => {
    if (viewed.includes(id)) return
    if (authed) {
      setViewed((prev) => [...prev, id])
      prefsApi.markViewed(id).catch(() => {})
    } else {
      setViewed((prev) => addViewed(prev, id))
    }
  }

  return {
    favorites,
    hidden,
    viewed,
    toggleFavorite,
    toggleHidden,
    clearHidden,
    markViewed,
  }
}
