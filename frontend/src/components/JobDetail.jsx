import { useEffect } from 'react'
import { formatDate, formatPay } from '../utils/format'

function JobDetail({ job, loading, error, onClose }) {
  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onClose])

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) onClose()
  }

  if (!job && !loading && !error) return null

  const salary = job ? formatPay(job) : null
  const posted = job ? formatDate(job.date_posted) : null
  const applyUrl = job ? job.job_url_direct || job.job_url : null

  return (
    <div className="modal-overlay" onClick={handleOverlayClick}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="job-detail-title">
        <div className="modal-header">
          {loading ? (
            <h2 id="job-detail-title">Loading job…</h2>
          ) : error ? (
            <h2 id="job-detail-title">Could not load job</h2>
          ) : (
            <h2 id="job-detail-title">{job.title}</h2>
          )}
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="modal-body">
          {loading && <p className="status">Loading…</p>}
          {error && <p className="status error">{error}</p>}
          {!loading && job && (
            <>
              <div className="job-subtitle">
                <span className="company">{job.company}</span>
                {job.location && <span className="location">{job.location}</span>}
              </div>
              <div className="job-badges">
                <span className="badge badge--source">{job.site}</span>
                {job.is_remote && <span className="badge badge--remote">Remote</span>}
                {job.job_type && <span className="badge badge--type">{job.job_type}</span>}
                {job.employment_type && (
                  <span className="badge badge--employment">{job.employment_type.toUpperCase()}</span>
                )}
                {salary && <span className="badge badge--salary">{salary}</span>}
                {posted && <span className="badge badge--posted">Posted {posted}</span>}
              </div>
              {applyUrl && (
                <div className="modal-actions">
                  <a className="apply-link" href={applyUrl} target="_blank" rel="noopener noreferrer">
                    Apply now
                  </a>
                </div>
              )}
              {job.description && (
                <div className="description" dangerouslySetInnerHTML={{ __html: job.description }} />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default JobDetail
