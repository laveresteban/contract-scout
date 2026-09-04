import { useEffect, useRef } from 'react'
import { eligibilityLabel, formatAnnualPay, formatDate, formatPay } from '../utils/format'

function JobDetail({ job, loading, error, onClose }) {
  const closeButtonRef = useRef(null)
  const modalRef = useRef(null)
  const previouslyFocused = useRef(null)

  const open = Boolean(job || loading || error)

  useEffect(() => {
    if (!open) return
    // Remember what had focus so we can restore it when the modal closes.
    previouslyFocused.current = document.activeElement
    closeButtonRef.current?.focus()
    return () => {
      if (previouslyFocused.current instanceof HTMLElement) {
        previouslyFocused.current.focus()
      }
    }
  }, [open])

  useEffect(() => {
    if (job) closeButtonRef.current?.focus()
  }, [job])

  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'Escape') {
        onClose()
        return
      }
      if (e.key !== 'Tab' || !modalRef.current) return
      // Trap focus within the modal.
      const focusable = modalRef.current.querySelectorAll(
        'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'
      )
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onClose])

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) onClose()
  }

  if (!open) return null

  const rawPay = job ? formatPay(job) : null
  const annualPay = job ? formatAnnualPay(job) : null
  const rawIsDistinct = rawPay && job?.interval && job.interval !== 'yearly'
  const eligibility = job ? eligibilityLabel(job) : null
  const posted = job ? formatDate(job.date_posted) : null
  const applyUrl = job ? job.job_url_direct || job.job_url : null

  return (
    <div className="modal-overlay" onClick={handleOverlayClick}>
      <div ref={modalRef} className="modal" role="dialog" aria-modal="true" aria-labelledby="job-detail-title">
        <div className="modal-header">
          {loading ? (
            <h2 id="job-detail-title">Loading job…</h2>
          ) : error ? (
            <h2 id="job-detail-title">Could not load job</h2>
          ) : (
            <h2 id="job-detail-title">{job.title}</h2>
          )}
          <button
            ref={closeButtonRef}
            type="button"
            className="modal-close"
            onClick={onClose}
            aria-label="Close"
          >
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
              {annualPay && (
                <div className="modal-comp">
                  <span className="comp-amount" title="Approximate yearly USD equivalent">{annualPay}</span>
                  {rawIsDistinct && <span className="comp-raw">{rawPay}</span>}
                </div>
              )}
              <div className="job-badges">
                <span className="badge badge--source">{job.site}</span>
                {job.is_remote && <span className="badge badge--remote">Remote</span>}
                {eligibility && (
                  <span className={`badge badge--eligibility badge--elig-${job.eligibility}`}>{eligibility}</span>
                )}
                {job.job_type && <span className="badge badge--type">{job.job_type}</span>}
                {job.employment_type && (
                  <span className="badge badge--employment">{job.employment_type.toUpperCase()}</span>
                )}
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
