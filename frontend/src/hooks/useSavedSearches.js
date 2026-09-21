import { useCallback, useEffect, useState } from 'react'
import { savedSearchApi } from '../api'
import {
  addSavedSearch as lsAdd,
  loadSavedSearches as lsLoad,
  removeSavedSearch as lsRemove,
} from '../utils/savedSearches'

function fromServer(row) {
  return {
    id: row.id,
    name: row.name,
    params: row.filters || {},
    alert_enabled: row.alert_enabled,
    alert_frequency: row.alert_frequency,
    alert_email: row.alert_email,
    last_alerted_at: row.last_alerted_at,
    server: true,
  }
}

function fromLocal(row) {
  return { ...row, params: row.params || {}, server: false }
}

/**
 * Saved searches backed by the server (with email-alert settings) when the
 * user is signed in, or by localStorage otherwise.
 */
export function useSavedSearches(user) {
  const authed = Boolean(user)
  const [searches, setSearches] = useState(() => lsLoad().map(fromLocal))

  const refresh = useCallback(() => {
    if (authed) {
      savedSearchApi
        .list()
        .then((rows) => setSearches(rows.map(fromServer)))
        .catch(() => {})
    } else {
      setSearches(lsLoad().map(fromLocal))
    }
  }, [authed])

  useEffect(() => {
    refresh()
  }, [refresh])

  const add = async (name, params, { alertEnabled = false, alertFrequency = 'daily' } = {}) => {
    if (authed) {
      const row = await savedSearchApi.create({
        name,
        filters: params,
        alert_enabled: alertEnabled,
        alert_frequency: alertFrequency,
      })
      setSearches((prev) => [fromServer(row), ...prev])
    } else {
      setSearches(lsAdd(lsLoad(), name, params).map(fromLocal))
    }
  }

  const update = async (id, patch) => {
    if (!authed) return
    const row = await savedSearchApi.update(id, patch)
    setSearches((prev) => prev.map((s) => (s.id === id ? fromServer(row) : s)))
  }

  const remove = async (id) => {
    if (authed) {
      await savedSearchApi.remove(id)
      setSearches((prev) => prev.filter((s) => s.id !== id))
    } else {
      setSearches(lsRemove(lsLoad(), id).map(fromLocal))
    }
  }

  return { searches, add, update, remove, refresh, supportsAlerts: authed }
}
