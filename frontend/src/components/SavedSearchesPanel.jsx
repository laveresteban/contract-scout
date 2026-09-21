import { useState } from 'react'
import { buildRecentLabel } from '../utils/filters'

const FREQUENCIES = [
  { value: 'immediate', label: 'Immediate' },
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
]

function describeParams(params) {
  return buildRecentLabel(params)
}

function SavedSearchesPanel({ searches, supportsAlerts, onRun, onDelete, onUpdate }) {
  const [open, setOpen] = useState(false)

  if (!searches.length) return null

  return (
    <section className="card saved-searches-panel">
      <div className="panel-header">
        <div>
          <span className="eyebrow">Your workspace</span>
          <h2>Saved searches</h2>
          <p>{searches.length} saved {searches.length === 1 ? 'search' : 'searches'} ready to run again.</p>
        </div>
        <button
          type="button"
          className="panel-toggle"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
        >
          {open ? 'Collapse' : 'View saved'}
        </button>
      </div>
      {open && (
        <>
          <ul className="saved-search-list">
            {searches.map((entry) => (
              <li key={entry.id} className="saved-search-row">
                <div className="saved-search-info">
                  <button
                    type="button"
                    className="saved-search-name"
                    onClick={() => onRun(entry)}
                    title="Run this search"
                  >
                    {entry.name}
                  </button>
                  <span className="saved-search-desc">{describeParams(entry.params)}</span>
                </div>
                {supportsAlerts && (
                  <div className="saved-search-alert">
                    <label className="alert-toggle">
                      <input
                        type="checkbox"
                        checked={!!entry.alert_enabled}
                        onChange={(e) => onUpdate(entry.id, { alert_enabled: e.target.checked })}
                      />
                      Email alerts
                    </label>
                    <select
                      value={entry.alert_frequency || 'daily'}
                      disabled={!entry.alert_enabled}
                      onChange={(e) => onUpdate(entry.id, { alert_frequency: e.target.value })}
                      aria-label="Alert frequency"
                    >
                      {FREQUENCIES.map((f) => (
                        <option key={f.value} value={f.value}>
                          {f.label}
                        </option>
                      ))}
                    </select>
                    {entry.alert_enabled && (
                      <input
                        type="email"
                        className="alert-email"
                        // Remount when the stored value changes so defaultValue stays in sync.
                        key={`alert-email-${entry.id}-${entry.alert_email || ''}`}
                        defaultValue={entry.alert_email || ''}
                        placeholder="Send to… (defaults to your account email)"
                        aria-label="Alert email address"
                        onBlur={(e) => {
                          const next = e.target.value.trim()
                          if (next !== (entry.alert_email || '')) {
                            onUpdate(entry.id, { alert_email: next || null })
                          }
                        }}
                      />
                    )}
                  </div>
                )}
                <button
                  type="button"
                  className="saved-search-delete"
                  onClick={() => onDelete(entry.id)}
                  aria-label={`Delete ${entry.name}`}
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
          {!supportsAlerts && (
            <p className="saved-search-hint">Sign in to sync saved searches and enable email alerts.</p>
          )}
        </>
      )}
    </section>
  )
}

export default SavedSearchesPanel
