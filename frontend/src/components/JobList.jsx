import JobCard from './JobCard'

function SkeletonCard() {
  return (
    <article className="job-card skeleton-card" aria-busy="true" aria-live="polite">
      <div className="skeleton skeleton--title" />
      <div className="skeleton skeleton--subtitle" />
      <div className="skeleton-row">
        <div className="skeleton skeleton--badge" />
        <div className="skeleton skeleton--badge" />
        <div className="skeleton skeleton--badge" />
      </div>
      <div className="skeleton skeleton--line" />
      <div className="skeleton skeleton--line" />
    </article>
  )
}

function JobList({ jobs, loading, error }) {
  if (loading) {
    return (
      <section className="job-list" aria-label="Loading jobs">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </section>
    )
  }

  if (error) {
    return (
      <p className="status error">
        <strong>Something went wrong.</strong>
        <br />
        {error}
      </p>
    )
  }

  if (!jobs || jobs.length === 0) {
    return <p className="status">No jobs found yet. Run a search above.</p>
  }

  return (
    <section className="job-list">
      {jobs.map((job) => (
        <JobCard key={job.id} job={job} />
      ))}
    </section>
  )
}

export default JobList
