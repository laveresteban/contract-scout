import { useMemo, useState } from 'react'
import { eligibilityLabel, formatAnnualPay, formatDate, formatPay, stripHtml } from '../utils/format'

function companyInitials(company) {
  return (company || 'Contract Scout')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()
}

function JobCard({ job, onSelect, isFavorite, isNew, isViewed, onToggleFavorite, onToggleHidden }) {
  const [expanded, setExpanded] = useState(false)

  const rawPay = formatPay(job)
  const annualPay = formatAnnualPay(job)
  // Show the raw rate only when it adds something beyond the yearly-equiv headline.
  const rawIsDistinct = rawPay && job.interval && job.interval !== 'yearly'
  const eligibility = eligibilityLabel(job)
  const posted = formatDate(job.date_posted)
  const applyUrl = job.job_url_direct || job.job_url
  const descriptionText = useMemo(() => stripHtml(job.description), [job.description])
  const hasLongDescription = descriptionText.length > 240
  const descriptionId = `job-description-${job.id}`

  return (
    <article
      className={`job-card${isViewed ? ' job-card--viewed' : ''}`}
      aria-label={`${job.title} at ${job.company}`}
    >
      <div className="job-header">
        <div className="job-header__main">
          <span className="company-mark" aria-hidden="true">{companyInitials(job.company)}</span>
          <div className="job-header__copy">
            <h3>
              <button type="button" className="job-title-button" onClick={() => onSelect?.(job.id)}>
                {job.title}
              </button>
            </h3>
            <div className="job-subtitle">
              <span className="company">{job.company}</span>
              {job.location && <span className="location">{job.location}</span>}
            </div>
          </div>
        </div>
        <div className="job-header__pay">
          {annualPay ? (
            <>
              <span className="comp-amount" title="Approximate yearly USD equivalent">{annualPay}</span>
              {rawIsDistinct && <span className="comp-raw">{rawPay}</span>}
            </>
          ) : (
            <span className="comp-amount comp-amount--muted">Pay undisclosed</span>
          )}
        </div>
      </div>

      <div className="job-badges">
        {isNew && <span className="badge badge--new">New</span>}
        {isViewed && <span className="badge badge--viewed">Viewed</span>}
        <span className="badge badge--source">{job.site}</span>
        {job.is_remote && <span className="badge badge--remote">Remote</span>}
        {eligibility && <span className={`badge badge--eligibility badge--elig-${job.eligibility}`}>{eligibility}</span>}
        {job.job_type && <span className="badge badge--type">{job.job_type}</span>}
        {job.employment_type && (
          <span className="badge badge--employment">{job.employment_type.toUpperCase()}</span>
        )}
        {posted && <span className="badge badge--posted">Posted {posted}</span>}
      </div>

      <div className="job-actions">
        <button
          type="button"
          className={`action-button ${isFavorite ? 'action-button--active' : ''}`}
          onClick={(e) => {
            e.stopPropagation()
            onToggleFavorite?.(job.id)
          }}
          aria-pressed={isFavorite}
          aria-label={isFavorite ? 'Remove from saved jobs' : 'Save job'}
        >
          {isFavorite ? 'Saved' : 'Save'}
        </button>
        <button
          type="button"
          className="action-button"
          onClick={(e) => {
            e.stopPropagation()
            onToggleHidden?.(job.id)
          }}
          aria-label="Hide job"
        >
          Hide
        </button>
        {applyUrl && (
          <a
            className="apply-link"
            href={applyUrl}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="View job posting (opens in a new tab)"
            onClick={(e) => e.stopPropagation()}
          >
            View job →
          </a>
        )}
      </div>

      {job.description && (
        <div className="description-block">
          <div
            id={descriptionId}
            className="description"
            style={{
              maxHeight: expanded || !hasLongDescription ? 'none' : '120px',
              overflow: expanded ? 'auto' : 'hidden',
            }}
          >
            {descriptionText}
          </div>
          {hasLongDescription && (
            <button
              type="button"
              className="expand-button"
              aria-expanded={expanded}
              aria-controls={descriptionId}
              onClick={(e) => {
                e.stopPropagation()
                setExpanded(!expanded)
              }}
            >
              {expanded ? 'Show less' : 'Show more'}
            </button>
          )}
        </div>
      )}
    </article>
  )
}

export default JobCard
