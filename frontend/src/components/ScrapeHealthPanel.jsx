import { useEffect, useState } from 'react'
import { getScrapeHealth } from '../api'
import { formatRelativeTime } from '../utils/format'

const SOURCE_LABELS = {
  major_boards: 'Major boards',
  remote_boards: 'Remote-first boards',
}

function ScrapeHealthPanel() {
  const [open, setOpen] = useState(false)
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = () => {
    setLoading(true)
    getScrapeHealth()
      .then(setHealth)
      .catch(() => setHealth(null))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (open && !health) load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  return (
    <section className="card scrape-health">
      <div className="scrape-health-header">
        <button
          type="button"
          className="scrape-health-toggle"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          {open ? '▾' : '▸'} Scraping status
        </button>
        {open && (
          <button type="button" className="scrape-health-refresh" onClick={load} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        )}
      </div>
      {open && (
        <div className="scrape-health-body">
          <p className="scrape-health-scheduler">
            Scheduler:{' '}
            {health?.scheduler_enabled
              ? `every ${health.interval_minutes} min${
                  health.next_run_at ? ` · next ${formatRelativeTime(health.next_run_at)}` : ''
                }`
              : 'disabled'}
          </p>
          {health?.sources?.length ? (
            <div className="scrape-health-table-wrap">
              <table className="scrape-health-table">
                <caption className="sr-only">Recent scraping results by source</caption>
                <thead>
                  <tr>
                    <th scope="col">Source</th>
                    <th scope="col">Status</th>
                    <th scope="col">Found</th>
                    <th scope="col">Stored</th>
                    <th scope="col">Pay</th>
                    <th scope="col">Hourly</th>
                    <th scope="col">Duration</th>
                    <th scope="col">Last run</th>
                  </tr>
                </thead>
                <tbody>
                  {health.sources.map((s) => (
                    <tr key={s.source}>
                      <td>{SOURCE_LABELS[s.source] || s.source}</td>
                      <td>
                        <span className={`health-status health-status--${s.last_status}`}>
                          {s.last_status || 'n/a'}
                        </span>
                      </td>
                      <td>{s.last_jobs_found}</td>
                      <td>{s.stored_jobs}</td>
                      <td>{s.pay_coverage}%</td>
                      <td>{s.hourly_coverage}%</td>
                      <td>{s.last_duration_ms != null ? `${s.last_duration_ms} ms` : '—'}</td>
                      <td title={s.last_error || ''}>
                        {s.last_run_at ? formatRelativeTime(s.last_run_at) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="status">No scrape runs recorded yet.</p>
          )}
        </div>
      )}
    </section>
  )
}

export default ScrapeHealthPanel
