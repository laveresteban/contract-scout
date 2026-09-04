import { useMemo, useState } from 'react'
import { eligibilityLabel, formatAnnualPay, formatDate, formatPay, stripHtml } from '../utils/format'

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

  return (
    <article
      className={`job-card${isViewed ? ' job-card--viewed' : ''}`}
      aria-label={`${job.title} at ${job.company}`}
      onClick={() => onSelect?.(job.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect?.(job.id)
        }
      }}
      role="button"
      tabIndex={0}
    >
      <div className="job-header">
        <div className="job-header__main">
          <h3>{job.title}</h3>
          <div className="job-subtitle">
            <span className="company">{job.company}</span>
            {job.location && <span className="location">{job.location}</span>}
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
            onClick={(e) => e.stopPropagation()}
          >
            View job →
          </a>
        )}
      </div>

      {job.description && (
        <div className="description-block">
          <div
            className="description"
            style={{
              maxHeight: expanded || !hasLongDescription ? 'none' : '120px',
              overflow: expanded ? 'auto' : 'hidden',
            }}
            dangerouslySetInnerHTML={{ __html: job.description }}
          />
          {hasLongDescription && (
            <button
              type="button"
              className="expand-button"
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
