import { useMemo, useState } from 'react'

function formatCurrency(amount, currency) {
  if (amount == null) return ''
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency || 'USD',
    maximumFractionDigits: 0,
  }).format(amount)
}

function stripHtml(html) {
  if (!html) return ''
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

function formatDate(dateString) {
  if (!dateString) return null
  const d = new Date(dateString)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatPay(job) {
  const parts = []
  if (job.min_amount != null) parts.push(formatCurrency(job.min_amount, job.currency))
  if (job.max_amount != null) parts.push(formatCurrency(job.max_amount, job.currency))
  if (!parts.length) return null
  let label = parts.join(' – ')
  if (job.interval) label += ` / ${job.interval}`
  return label
}

function JobCard({ job }) {
  const [expanded, setExpanded] = useState(false)

  const salary = formatPay(job)
  const posted = formatDate(job.date_posted)
  const applyUrl = job.job_url_direct || job.job_url
  const descriptionText = useMemo(() => stripHtml(job.description), [job.description])
  const hasLongDescription = descriptionText.length > 240

  return (
    <article className="job-card">
      <div className="job-header">
        <h3>{job.title}</h3>
        <a className="apply-link" href={applyUrl} target="_blank" rel="noopener noreferrer">
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
              onClick={() => setExpanded(!expanded)}
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
