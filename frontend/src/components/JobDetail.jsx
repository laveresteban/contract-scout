import { useEffect, useRef, useState } from 'react'
import { eligibilityLabel, formatDate, formatRelativeTime, getPayDisplay } from '../utils/format'
import { evaluateJob, tierLabel } from '../utils/quality'
import JobDescription from './JobDescription'

function JobDetail({ job, loading, error, onClose, onVerify }) {
  const [verifying, setVerifying] = useState(false)
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
    if (!open) return
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
  }, [onClose, open])

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) onClose()
  }

  if (!open) return null

  const pay = job ? getPayDisplay(job) : null
  const eligibility = job ? eligibilityLabel(job) : null
  const posted = job ? formatDate(job.date_posted) : null
  const applyUrl = job ? job.job_url_direct || job.job_url : null
  const assessment = job ? evaluateJob(job) : null
  const remoteUnverified = assessment?.remoteConfidence === 'unverified'

  const handleRecheck = async () => {
    if (!job || verifying || !onVerify) return
    setVerifying(true)
    try {
      await onVerify(job.id, { force: true })
    } finally {
      setVerifying(false)
    }
  }

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
              {pay?.hasPay ? (
                <div className="modal-comp">
                  <div className="modal-comp__figures">
                    {pay.annual && (
                      <span className="comp-amount" title="Approximate yearly USD equivalent">{pay.annual}</span>
                    )}
                    {pay.rawIsDistinct && (
                      <span className="comp-raw">{pay.intervalLabel}: {pay.raw}</span>
                    )}
                  </div>
                  <span className="modal-comp__tag">Compensation</span>
                </div>
              ) : (
                <div className="modal-comp modal-comp--empty">
                  <span className="comp-amount comp-amount--muted">Pay not disclosed</span>
                  <span className="modal-comp__tag">Re-check the posting — we scrape pay from the live page</span>
                </div>
              )}
              <div className="job-badges">
                <span className="badge badge--source">{job.site}</span>
                {job.is_remote && (
                  remoteUnverified ? (
                    <span className="badge badge--remote-warn">Remote?</span>
                  ) : (
                    <span className="badge badge--remote">Remote</span>
                  )
                )}
                {eligibility && (
                  <span className={`badge badge--eligibility badge--elig-${job.eligibility}`}>{eligibility}</span>
                )}
                {job.job_type && <span className="badge badge--type">{job.job_type}</span>}
                {job.employment_type && (
                  <span className="badge badge--employment">{job.employment_type.toUpperCase()}</span>
                )}
                {posted && <span className="badge badge--posted">Posted {posted}</span>}
              </div>
              {assessment && (assessment.flags.length > 0 || assessment.tier === 'trusted') && (
                <div className={`quality-panel quality-panel--${assessment.tier}`}>
                  <div className="quality-panel__header">
                    <span className="quality-panel__tier">{tierLabel(assessment.tier)}</span>
                    <span className="quality-panel__score" title="Confidence score">
                      {assessment.score}/100
                    </span>
                  </div>
                  {job.verify_checked_at && (
                    <p className="quality-panel__checked">
                      Source re-checked {formatRelativeTime(job.verify_checked_at)}
                    </p>
                  )}
                  {assessment.flags.length > 0 ? (
                    <ul className="quality-panel__flags">
                      {assessment.flags.map((flag) => (
                        <li key={flag.id} className={`quality-flag quality-flag--${flag.level}`}>
                          <span className="quality-flag__label">{flag.label}</span>
                          <span className="quality-flag__detail">{flag.detail}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="quality-panel__clear">
                      No red flags — remote, dated, and detailed.
                    </p>
                  )}
                </div>
              )}
              {applyUrl ? (
                <div className="modal-actions">
                  <a className="apply-link" href={applyUrl} target="_blank" rel="noopener noreferrer" aria-label="Apply now (opens in a new tab)">
                    Apply now
                  </a>
                  {onVerify && (
                    <button
                      type="button"
                      className="recheck-button"
                      onClick={handleRecheck}
                      disabled={verifying}
                    >
                      {verifying ? 'Re-checking…' : 'Re-check posting'}
                    </button>
                  )}
                  <span className="modal-actions__hint">Opens the original posting — confirm it’s still live.</span>
                </div>
              ) : (
                <p className="status error modal-no-link">No original posting link is available for this listing.</p>
              )}
              {job.description ? (
                <JobDescription className="description" html={job.description} />
              ) : (
                <p className="status empty-state">This listing has no description.</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default JobDetail
