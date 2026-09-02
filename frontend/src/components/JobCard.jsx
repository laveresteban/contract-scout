import { useMemo, useState } from 'react'
import { formatDate, formatPay, stripHtml } from '../utils/format'

function JobCard({ job, onSelect, isFavorite, onToggleFavorite, onToggleHidden }) {
  const [expanded, setExpanded] = useState(false)

  const salary = formatPay(job)
  const posted = formatDate(job.date_posted)
  const applyUrl = job.job_url_direct || job.job_url
  const descriptionText = useMemo(() => stripHtml(job.description), [job.description])
  const hasLongDescription = descriptionText.length > 240

  return (
    <article
      className="job-card"
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
        <h3>{job.title}</h3>
        <a
          className="apply-link"
          href={applyUrl}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
        >
          View job
        </a>
      </div>

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

      <div className="job-actions">
        <button
          type="button"
          className={`action-button ${isFavorite ? 'action-button--active' : ''}`}
          onClick={(e) => {
            e.stopPropagation()
            onToggleFavorite?.(job.id)
          }}
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
        >
          Hide
        </button>
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
