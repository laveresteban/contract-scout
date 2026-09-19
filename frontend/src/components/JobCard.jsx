import { useMemo, useState } from 'react'
import { eligibilityLabel, formatDate, getPayDisplay, stripHtml } from '../utils/format'
import { evaluateJob, primaryWarning } from '../utils/quality'
import JobDescription from './JobDescription'

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

  const pay = getPayDisplay(job)
  const eligibility = eligibilityLabel(job)
  const posted = formatDate(job.date_posted)
  const applyUrl = job.job_url_direct || job.job_url

  const assessment = useMemo(() => evaluateJob(job), [job])
  const warning = primaryWarning(assessment)
  const remoteUnverified = assessment.remoteConfidence === 'unverified'

  const descriptionText = useMemo(() => stripHtml(job.description), [job.description])
  const hasLongDescription = descriptionText.length > 240
  const descriptionId = `job-description-${job.id}`
  const isExpired = assessment.flags.some((flag) => flag.id === 'expired')

  return (
    <article
      className={`job-card${isViewed ? ' job-card--viewed' : ''}${isExpired ? ' job-card--flagged' : ''}`}
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
              <span className="company">{job.company || 'Undisclosed company'}</span>
              {job.location && <span className="location">{job.location}</span>}
            </div>
          </div>
        </div>
        <div className="job-header__pay">
          {pay.annual ? (
            <>
              <span className="comp-amount" title="Approximate yearly USD equivalent">{pay.annual}</span>
              {pay.rawIsDistinct && <span className="comp-raw">{pay.raw}</span>}
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
        {job.is_remote && (
          remoteUnverified ? (
            <span className="badge badge--remote-warn" title="Tagged remote, but the description suggests otherwise">
              Remote?
            </span>
          ) : (
            <span className="badge badge--remote">Remote</span>
          )
        )}
        {eligibility && <span className={`badge badge--eligibility badge--elig-${job.eligibility}`}>{eligibility}</span>}
        {job.job_type && <span className="badge badge--type">{job.job_type}</span>}
        {job.employment_type && (
          <span className="badge badge--employment">{job.employment_type.toUpperCase()}</span>
        )}
        {posted && <span className="badge badge--posted">Posted {posted}</span>}
      </div>

      {warning && (
        <div className={`job-alert job-alert--${warning.level}`} role="note">
          <span className="job-alert__label">{warning.label}</span>
          <span className="job-alert__detail">{warning.detail}</span>
          {assessment.flags.length > 1 && (
            <span className="job-alert__more">+{assessment.flags.length - 1} more</span>
          )}
        </div>
      )}

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
            <JobDescription html={job.description} />
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
