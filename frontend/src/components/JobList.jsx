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

function JobList({
  jobs,
  loading,
  loadingMore,
  error,
  hasMore,
  onLoadMore,
  onSelectJob,
  onRetry,
  favorites,
  hidden,
  viewMode,
  onToggleFavorite,
  onToggleHidden,
}) {
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
      <div className="status error error-card">
        <strong>Could not load jobs.</strong>
        <p>{error}</p>
        {onRetry && (
          <button onClick={onRetry} className="retry-button" type="button">
            Try again
          </button>
        )}
      </div>
    )
  }

  const hiddenSet = new Set(hidden)
  const favoriteSet = new Set(favorites)
  const visibleJobs = jobs.filter((job) => {
    if (hiddenSet.has(job.id)) return false
    if (viewMode === 'favorites') return favoriteSet.has(job.id)
    return true
  })

  if (!visibleJobs.length) {
    let message = 'No jobs found yet. Run a search above.'
    if (viewMode === 'favorites') {
      message = 'No saved jobs yet. Save jobs from the results to see them here.'
    } else if (jobs.length > 0) {
      message = 'No jobs match the current filters. Try adjusting your search.'
    }
    return <p className="status empty-state">{message}</p>
  }

  return (
    <section className="job-list">
      {visibleJobs.map((job) => (
        <JobCard
          key={job.id}
          job={job}
          onSelect={onSelectJob}
          isFavorite={favoriteSet.has(job.id)}
          onToggleFavorite={onToggleFavorite}
          onToggleHidden={onToggleHidden}
        />
      ))}
      {hasMore && viewMode !== 'favorites' && (
        <div className="load-more">
          <button onClick={onLoadMore} disabled={loadingMore} className="load-more-button">
            {loadingMore ? 'Loading more…' : 'Load more jobs'}
          </button>
        </div>
      )}
      {!hasMore && !loadingMore && viewMode !== 'favorites' && (
        <p className="status end-of-results">No more jobs.</p>
      )}
    </section>
  )
}

export default JobList
