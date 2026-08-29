function formatCurrency(amount, currency) {
  if (amount == null) return ''
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency || 'USD',
    maximumFractionDigits: 0,
  }).format(amount)
}

function JobCard({ job }) {
  const salary = []
  if (job.min_amount != null) salary.push(formatCurrency(job.min_amount, job.currency))
  if (job.max_amount != null) salary.push(formatCurrency(job.max_amount, job.currency))
  const salaryLabel = salary.length ? `${salary.join(' – ')}${job.interval ? ` / ${job.interval}` : ''}` : null

  return (
    <article className="job-card">
      <h3>{job.title}</h3>
      <div className="job-meta">
        <span>{job.company}</span>
        <span>{job.location || 'Remote'}</span>
        <span>{job.site}</span>
        {job.is_remote && <span>Remote</span>}
        {job.employment_type && <span>{job.employment_type.toUpperCase()}</span>}
        {job.job_type && <span>{job.job_type}</span>}
        {salaryLabel && <span>{salaryLabel}</span>}
      </div>
      {job.description && (
        <div
          className="description"
          dangerouslySetInnerHTML={{ __html: job.description }}
        />
      )}
      <a href={job.job_url_direct || job.job_url} target="_blank" rel="noopener noreferrer">
        View job
      </a>
    </article>
  )
}

export default JobCard
