import { useEffect, useMemo, useState } from 'react'
import SearchFilters from './components/SearchFilters'
import JobList from './components/JobList'
import JobDetail from './components/JobDetail'
import ThemeToggle from './components/ThemeToggle'
import { getJob, listJobs, listSources, scrapeJobs } from './api'
import {
  addRecentSearch,
  deserializeFilters,
  loadRecentSearches,
  serializeFilters,
} from './utils/filters'
import { downloadFile, jobsToCsv } from './utils/export'
import { clearHidden, loadFavorites, loadHidden, loadTheme, saveTheme, toggleFavorite, toggleHidden } from './utils/prefs'

const PAGE_SIZE = 25

function App() {
  const [jobs, setJobs] = useState([])
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState(null)
  const [lastSearch, setLastSearch] = useState(null)
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

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    saveTheme(theme)
  }, [theme])

  useEffect(() => {
    listSources()
      .then((data) => setSources(data))
      .catch(() => setSources([]))

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

  const updateUrl = (params) => {
    const qs = serializeFilters(params)
    window.history.replaceState({}, '', qs ? `?${qs}` : window.location.pathname)
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
  }

  const handleLoadMore = () => {
    if (lastSearch && !loadingMore) {
      fetchJobs(lastSearch, { append: true })
    }
  }

  const handleSelectJob = (id) => setSelectedJobId(id)
  const handleCloseDetail = () => setSelectedJobId(null)

  const handleToggleFavorite = (id) => setFavorites((prev) => toggleFavorite(prev, id))
  const handleToggleHidden = (id) => setHidden((prev) => toggleHidden(prev, id))
  const handleClearHidden = () => setHidden(clearHidden())
  const handleToggleTheme = () => setTheme((prev) => (prev === 'light' ? 'dark' : 'light'))

  const handleExportCsv = () => {
    const csv = jobsToCsv(visibleJobs)
    downloadFile(csv, `contract-scout-jobs-${new Date().toISOString().slice(0, 10)}.csv`, 'text/csv')
  }

  const handleExportJson = () => {
    const json = JSON.stringify(visibleJobs, null, 2)
    downloadFile(json, `contract-scout-jobs-${new Date().toISOString().slice(0, 10)}.json`, 'application/json')
  }

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
    } catch {
      // fallback for older browsers
      const input = document.createElement('input')
      input.value = window.location.href
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      document.body.removeChild(input)
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
          loading={loading}
          sources={sources}
          initialParams={initialParams}
          recentSearches={recentSearches}
        />
      </section>

      <section className="card">
        <div className="results-header">
          <h2>
            {viewMode === 'favorites' ? 'Saved jobs' : 'Jobs'} ({visibleJobs.length})
          </h2>
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
        <JobList
          jobs={jobs}
          loading={loading}
          loadingMore={loadingMore}
          error={error}
          hasMore={hasMore}
          onLoadMore={handleLoadMore}
          onSelectJob={handleSelectJob}
          favorites={favorites}
          hidden={hidden}
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
    </div>
  )
}

export default App
