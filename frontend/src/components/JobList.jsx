import JobCard from './JobCard'

function JobList({ jobs, loading, error }) {
  if (loading) return <p className="status">Loading jobs…</p>
  if (error) return <p className="status error">{error}</p>
  if (!jobs || jobs.length === 0) return <p className="status">No jobs found yet. Run a search above.</p>

  return (
    <section className="job-list">
      {jobs.map((job) => (
        <JobCard key={job.id} job={job} />
      ))}
    </section>
  )
}

export default JobList
