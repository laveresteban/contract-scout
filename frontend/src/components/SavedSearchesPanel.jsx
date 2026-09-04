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
  if (!searches.length) return null

  return (
    <section className="card saved-searches-panel">
      <h2>Saved searches</h2>
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
    </section>
  )
}

export default SavedSearchesPanel
