import { useEffect, useMemo, useRef, useState } from 'react'
import SearchFilters from './components/SearchFilters'
import JobList from './components/JobList'
import JobDetail from './components/JobDetail'
import PayInsights from './components/PayInsights'
import ThemeToggle from './components/ThemeToggle'
import ToastContainer from './components/Toast'
import { getJob, getJobStats, listJobs, listSources, scrapeJobs } from './api'
import {
  addRecentSearch,
  deserializeFilters,
  loadRecentSearches,
  serializeFilters,
} from './utils/filters'
import { downloadFile, jobsToCsv } from './utils/export'
import { formatRelativeTime } from './utils/format'
import {
  clearHidden,
  loadFavorites,
  loadHidden,
  loadLastVisit,
  loadTheme,
  saveLastVisit,
  saveTheme,
  toggleFavorite,
  toggleHidden,
} from './utils/prefs'

const PAGE_SIZE = 25

function App() {
  const [jobs, setJobs] = useState([])
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState(null)
  const [lastSearch, setLastSearch] = useState(null)
  const [jobStats, setJobStats] = useState(null)
  const [recentSearches, setRecentSearches] = useState(() => loadRecentSearches())
  const [initialParams, setInitialParams] = useState(() => deserializeFilters(window.location.search))
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [selectedJobId, setSelectedJobId] = useState(null)
  const [selectedJob, setSelectedJob] = useState(null)
  const [selectedJobLoading, setSelectedJobLoading] = useState(false)
  const [selectedJobError, setSelectedJobError] = useState(null)
  const [favorites, setFavorites] = useState(() => loadFavorites())
  const [hidden, setHidden] = useState(() => loadHidden())
  const [viewMode, setViewMode] = useState('all')
  const [theme, setTheme] = useState(() => loadTheme())
  const [lastVisit] = useState(() => loadLastVisit())
  const [toasts, setToasts] = useState([])
  const toastIdRef = useRef(0)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    saveTheme(theme)
  }, [theme])

  useEffect(() => {
    const onBeforeUnload = () => saveLastVisit(Date.now())
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [])

  useEffect(() => {
    listSources()
      .then((data) => setSources(data))
      .catch(() => setSources([]))

    fetchJobStats()

    if (window.location.search) {
      fetchJobs(deserializeFilters(window.location.search))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!selectedJobId) {
      setSelectedJob(null)
      setSelectedJobError(null)
      return
    }
    setSelectedJobLoading(true)
    setSelectedJob(null)
    setSelectedJobError(null)
    getJob(selectedJobId)
      .then((data) => setSelectedJob(data))
      .catch((err) => setSelectedJobError(err.message || 'Could not load job details.'))
      .finally(() => setSelectedJobLoading(false))
  }, [selectedJobId])

  const hiddenSet = useMemo(() => new Set(hidden), [hidden])
  const favoriteSet = useMemo(() => new Set(favorites), [favorites])

  const visibleJobs = useMemo(() => {
    return jobs.filter((job) => {
      if (hiddenSet.has(job.id)) return false
      if (viewMode === 'favorites') return favoriteSet.has(job.id)
      return true
    })
  }, [jobs, hiddenSet, favoriteSet, viewMode])

  const companies = useMemo(() => {
    const names = new Set()
    jobs.forEach((job) => {
      if (job.company) names.add(job.company)
    })
    return [...names].sort()
  }, [jobs])

  const updateUrl = (params) => {
    const qs = serializeFilters(params)
    window.history.replaceState({}, '', qs ? `?${qs}` : window.location.pathname)
  }

  const fetchJobStats = async () => {
    try {
      const stats = await getJobStats()
      setJobStats(stats)
    } catch {
      setJobStats(null)
    }
  }

  const showToast = (message, type = 'info') => {
    const id = ++toastIdRef.current
    setToasts((prev) => [...prev, { id, message, type }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id))
    }, 3000)
  }

  const handleCloseToast = (id) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id))
  }

  const fetchJobs = async (params, { scrape = false, append = false } = {}) => {
    if (append) {
      setLoadingMore(true)
    } else {
      setLoading(true)
      setOffset(0)
    }
    setError(null)
    if (!append) setLastSearch(params)

    const currentOffset = append ? offset : 0

    try {
      if (scrape) {
        const scrapeParams = { ...params }
        delete scrapeParams.source
        await scrapeJobs({ ...scrapeParams, results_wanted: PAGE_SIZE })
      }
      const fetched = await listJobs({
        q: params.query,
        is_remote: true,
        is_us: true,
        job_type: params.job_type,
        employment_type: params.employment_type,
        min_pay: params.min_pay,
        max_pay: params.max_pay,
        pay_interval: params.pay_interval,
        source: params.source,
        company: params.company,
        sort_by: params.sort_by,
        sort_order: params.sort_order,
        limit: PAGE_SIZE,
        offset: currentOffset,
      })
      setJobs((prev) => (append ? [...prev, ...fetched] : fetched))
      setHasMore(fetched.length === PAGE_SIZE)
      setOffset(currentOffset + fetched.length)
    } catch (err) {
      setError(err.message || 'Something went wrong.')
    } finally {
      if (append) {
        setLoadingMore(false)
      } else {
        setLoading(false)
      }
    }
  }

  const handleSearch = async (params) => {
    updateUrl(params)
    setInitialParams(params)
    setRecentSearches((prev) => addRecentSearch(prev, params))
    setViewMode('all')
    await fetchJobs(params, { scrape: true })
    await fetchJobStats()
  }

  const handleLoadMore = () => {
    if (lastSearch && !loadingMore) {
      fetchJobs(lastSearch, { append: true })
    }
  }

  const handleRetry = () => {
    if (lastSearch) {
      handleSearch(lastSearch)
    }
  }

  const handleSelectJob = (id) => setSelectedJobId(id)
  const handleCloseDetail = () => setSelectedJobId(null)

  const handleToggleFavorite = (id) => {
    const removing = favoriteSet.has(id)
    setFavorites((prev) => toggleFavorite(prev, id))
    showToast(removing ? 'Removed from saved jobs' : 'Saved job')
  }

  const handleToggleHidden = (id) => {
    const removing = hiddenSet.has(id)
    setHidden((prev) => toggleHidden(prev, id))
    showToast(removing ? 'Job shown' : 'Job hidden')
  }

  const handleClearHidden = () => {
    setHidden(clearHidden())
    showToast('Hidden jobs shown')
  }
  const handleToggleTheme = () => setTheme((prev) => (prev === 'light' ? 'dark' : 'light'))

  const handleExportCsv = () => {
    const csv = jobsToCsv(visibleJobs)
    downloadFile(csv, `contract-scout-jobs-${new Date().toISOString().slice(0, 10)}.csv`, 'text/csv')
    showToast('CSV exported', 'success')
  }

  const handleExportJson = () => {
    const json = JSON.stringify(visibleJobs, null, 2)
    downloadFile(json, `contract-scout-jobs-${new Date().toISOString().slice(0, 10)}.json`, 'application/json')
    showToast('JSON exported', 'success')
  }

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
      showToast('Search link copied', 'success')
    } catch {
      // fallback for older browsers
      const input = document.createElement('input')
      input.value = window.location.href
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      document.body.removeChild(input)
      showToast('Search link copied', 'success')
    }
  }

  return (
    <div className="container">
      <header>
        <div className="header-content">
          <h1>Contract Scout</h1>
          <ThemeToggle theme={theme} onToggle={handleToggleTheme} />
        </div>
        <p>Remote US contract jobs for software engineers and tech professionals.</p>
      </header>

      <section className="card">
        <SearchFilters
          onSearch={handleSearch}
          onShowToast={showToast}
          loading={loading}
          sources={sources}
          companies={companies}
          initialParams={initialParams}
          recentSearches={recentSearches}
        />
      </section>

      <section className="card">
        <div className="results-header">
          <div className="results-title">
            <h2>
              {viewMode === 'favorites' ? 'Saved jobs' : 'Jobs'} ({visibleJobs.length})
            </h2>
            {jobStats?.last_scraped && (
              <span className="last-scraped" title={new Date(jobStats.last_scraped).toLocaleString()}>
                Last scraped {formatRelativeTime(jobStats.last_scraped)}
              </span>
            )}
          </div>
          <div className="results-actions">
            <select
              value={viewMode}
              onChange={(e) => setViewMode(e.target.value)}
              className="view-mode-select"
              aria-label="View mode"
            >
              <option value="all">All jobs</option>
              <option value="favorites">Saved jobs</option>
            </select>
            {hidden.length > 0 && (
              <button onClick={handleClearHidden} className="clear-hidden-button">
                Show {hidden.length} hidden
              </button>
            )}
            {jobs.length > 0 && (
              <>
                <button onClick={handleExportCsv} className="export-button" title="Export CSV">
                  CSV
                </button>
                <button onClick={handleExportJson} className="export-button" title="Export JSON">
                  JSON
                </button>
              </>
            )}
            <button onClick={handleCopyLink} className="copy-link-button" title="Copy search link">
              Copy link
            </button>
            {lastSearch && !loading && (
              <button onClick={() => handleSearch(lastSearch)}>Refresh</button>
            )}
          </div>
        </div>
        {visibleJobs.length > 0 && <PayInsights jobs={visibleJobs} />}
        <JobList
          jobs={jobs}
          loading={loading}
          loadingMore={loadingMore}
          error={error}
          hasMore={hasMore}
          onLoadMore={handleLoadMore}
          onSelectJob={handleSelectJob}
          onRetry={handleRetry}
          favorites={favorites}
          hidden={hidden}
          lastVisit={lastVisit}
          viewMode={viewMode}
          onToggleFavorite={handleToggleFavorite}
          onToggleHidden={handleToggleHidden}
        />
      </section>

      <JobDetail
        job={selectedJob}
        loading={selectedJobLoading}
        error={selectedJobError}
        onClose={handleCloseDetail}
      />

      <ToastContainer toasts={toasts} onClose={handleCloseToast} />
    </div>
  )
}

export default App
