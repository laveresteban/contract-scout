import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import SearchFilters from './components/SearchFilters'
import JobList from './components/JobList'
import JobDetail from './components/JobDetail'
import PayInsights from './components/PayInsights'
import ThemeToggle from './components/ThemeToggle'
import ToastContainer from './components/Toast'
import AuthBar from './components/AuthBar'
import SavedSearchesPanel from './components/SavedSearchesPanel'
import ScrapeHealthPanel from './components/ScrapeHealthPanel'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { usePrefs } from './hooks/usePrefs'
import { useSavedSearches } from './hooks/useSavedSearches'
import { getHiddenCount, getJob, getJobStats, listJobs, listSources, scrapeJobs, verifyJob, verifyJobs } from './api'
import {
  addRecentSearch,
  deserializeFilters,
  loadRecentSearches,
  serializeFilters,
} from './utils/filters'
import { downloadFile, jobsToCsv } from './utils/export'
import { formatRelativeTime } from './utils/format'
import { dedupeJobs, mergeUniqueJobs } from './utils/jobs'
import { evaluateJob } from './utils/quality'
import { loadLastVisit, loadTheme, saveLastVisit, saveTheme } from './utils/prefs'

const PAGE_SIZE = 25
const SCRAPE_RESULTS_WANTED = 100

function AppContent({ toasts, showToast, onCloseToast }) {
  const { user } = useAuth()
  const prefs = usePrefs(user)
  const savedSearches = useSavedSearches(user)

  const [jobs, setJobs] = useState([])
  const [total, setTotal] = useState(0)
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
  const fetchIdRef = useRef(0)
  const autoVerifyAttempted = useRef(new Set())
  const [selectedJob, setSelectedJob] = useState(null)
  const [selectedJobLoading, setSelectedJobLoading] = useState(false)
  const [selectedJobError, setSelectedJobError] = useState(null)
  const [viewMode, setViewMode] = useState('all')
  const [hideRisky, setHideRisky] = useState(false)
  // Short-list guardrail: how many query matches the remote+US filters hide, and
  // whether the user has opted to include them.
  const [hiddenCount, setHiddenCount] = useState(0)
  const [includeIneligible, setIncludeIneligible] = useState(false)
  const [theme, setTheme] = useState(() => loadTheme())
  const [lastVisit] = useState(() => loadLastVisit())
  const [announcement, setAnnouncement] = useState('')
  const announce = (message) => setAnnouncement(message)

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
      fetchJobs(deserializeFilters(window.location.search), { shouldAnnounce: false })
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

  const hiddenSet = useMemo(() => new Set(prefs.hidden), [prefs.hidden])
  const favoriteSet = useMemo(() => new Set(prefs.favorites), [prefs.favorites])

  // Assess each job once; reused for the risky filter and the count badge.
  const riskyIds = useMemo(() => {
    const set = new Set()
    jobs.forEach((job) => {
      if (evaluateJob(job).tier === 'risky') set.add(job.id)
    })
    return set
  }, [jobs])

  const visibleJobs = useMemo(() => {
    return jobs.filter((job) => {
      if (hiddenSet.has(job.id)) return false
      if (hideRisky && riskyIds.has(job.id)) return false
      if (viewMode === 'favorites') return favoriteSet.has(job.id)
      return true
    })
  }, [jobs, hiddenSet, favoriteSet, viewMode, hideRisky, riskyIds])

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

  const fetchJobs = async (
    params,
    { scrape = false, append = false, shouldAnnounce = true, includeIneligible: includeOverride } = {},
  ) => {
    const includeAll = includeOverride ?? includeIneligible
    const fetchId = ++fetchIdRef.current

    if (append) {
      setLoadingMore(true)
    } else {
      setLoading(true)
      setLoadingMore(false)
      setOffset(0)
    }
    setError(null)
    if (!append) setLastSearch(params)
    if (shouldAnnounce) announce('Loading jobs')

    const currentOffset = append ? offset : 0

    try {
      if (scrape) {
        const scrapeParams = { ...params }
        if (scrapeParams.source) scrapeParams.sources = [scrapeParams.source]
        delete scrapeParams.source
        await scrapeJobs({ ...scrapeParams, results_wanted: SCRAPE_RESULTS_WANTED })
      }
      const { jobs: fetchedJobs, total: totalCount } = await listJobs({
        q: params.query,
        location: params.location,
        is_remote: true,
        is_us: true,
        include_ineligible: includeAll ? true : undefined,
        job_type: params.job_type,
        employment_type: params.employment_type,
        min_yearly: params.min_yearly,
        max_yearly: params.max_yearly,
        source: params.source,
        company: params.company,
        sort_by: params.sort_by,
        sort_order: params.sort_order,
        limit: PAGE_SIZE,
        offset: currentOffset,
      })
      if (fetchId !== fetchIdRef.current) return
      const fetched = dedupeJobs(fetchedJobs)
      setJobs((prev) => (append ? mergeUniqueJobs(prev, fetched) : fetched))
      setTotal(totalCount)
      // Advance by the API page size, not the number of unique cards. This
      // prevents duplicate-heavy pages from repeatedly being requested.
      setHasMore(currentOffset + fetchedJobs.length < totalCount)
      setOffset(currentOffset + fetchedJobs.length)
      if (!append && !includeAll) {
        getHiddenCount({
          q: params.query,
          job_type: params.job_type,
          employment_type: params.employment_type,
          min_yearly: params.min_yearly,
          max_yearly: params.max_yearly,
          source: params.source,
          company: params.company,
        })
          .then((res) => {
            if (fetchId === fetchIdRef.current) setHiddenCount(res.hidden || 0)
          })
          .catch(() => {})
      } else if (includeAll) {
        setHiddenCount(0)
      }
      if (shouldAnnounce) {
        if (fetched.length === 0 && !append) {
          announce('No jobs found for this search')
        } else {
          announce(`Loaded ${append ? jobs.length + fetched.length : fetched.length} of ${totalCount} jobs`)
        }
      }
    } catch (err) {
      setError(err.message || 'Something went wrong.')
      if (shouldAnnounce) announce(`Error: ${err.message || 'Something went wrong.'}`)
    } finally {
      if (fetchId === fetchIdRef.current) {
        if (append) {
          setLoadingMore(false)
        } else {
          setLoading(false)
        }
      }
    }
  }

  const handleSearch = async (params) => {
    updateUrl(params)
    setInitialParams(params)
    setRecentSearches((prev) => addRecentSearch(prev, params))
    setViewMode('all')
    // A fresh search re-applies the eligibility filters (and re-measures what
    // they hide) rather than carrying over a prior "show all" opt-in.
    setIncludeIneligible(false)
    await fetchJobs(params, { scrape: true, includeIneligible: false })
    await fetchJobStats()
  }

  // Short-list guardrail: loosen (or restore) the remote+US filters in place.
  const handleToggleIneligible = () => {
    const next = !includeIneligible
    setIncludeIneligible(next)
    if (lastSearch) {
      fetchJobs(lastSearch, { scrape: false, includeIneligible: next })
    }
  }

  const handleLoadMore = () => {
    if (lastSearch && !loadingMore) {
      fetchJobs(lastSearch, { append: true })
    }
  }

  const handleQueryChange = (params) => {
    if (!params.query || params.query.length < 2) return
    fetchJobs(params, { scrape: false, shouldAnnounce: false })
  }

  const handleRetry = () => {
    if (lastSearch) handleSearch(lastSearch)
  }

  const handleSelectJob = (id) => {
    setSelectedJobId(id)
    prefs.markViewed(id)
  }
  const handleCloseDetail = useCallback(() => setSelectedJobId(null), [])

  // Merge one or more verification results into the job list and the open modal.
  const applyVerifications = useCallback((resultsById) => {
    const toPatch = (result) => {
      const patch = {
        verify_status: result.status,
        verify_detail: result.detail,
        verify_checked_at: result.checked_at,
        verify_http_status: result.http_status,
      }
      // The verify pass also scrapes pay off the live page; fold it in so the
      // card reflects a rate we didn't have from the original scrape.
      if (result.normalized_min_yearly != null || result.normalized_max_yearly != null) {
        patch.min_amount = result.min_amount
        patch.max_amount = result.max_amount
        patch.currency = result.currency
        patch.interval = result.interval
        patch.normalized_min_yearly = result.normalized_min_yearly
        patch.normalized_max_yearly = result.normalized_max_yearly
      }
      return patch
    }
    setJobs((prev) =>
      prev.map((job) => (resultsById[job.id] ? { ...job, ...toPatch(resultsById[job.id]) } : job))
    )
    setSelectedJob((prev) =>
      prev && resultsById[prev.id] ? { ...prev, ...toPatch(resultsById[prev.id]) } : prev
    )
  }, [])

  const applyVerification = (id, result) => applyVerifications({ [id]: result })

  // Auto-verify the loaded page in the background: confirm which postings are
  // still live before the user commits to one. Best-effort and silent — only
  // jobs we haven't checked, one batched call, debounced so typing doesn't
  // trigger a flurry of outbound fetches.
  useEffect(() => {
    const pending = jobs
      .filter((job) => !job.verify_status || job.verify_status === 'unverified')
      .filter((job) => !autoVerifyAttempted.current.has(job.id))
      .slice(0, 25)
      .map((job) => job.id)
    if (pending.length === 0) return undefined

    const timer = setTimeout(async () => {
      pending.forEach((id) => autoVerifyAttempted.current.add(id))
      try {
        const { results } = await verifyJobs(pending)
        if (results && Object.keys(results).length) applyVerifications(results)
      } catch {
        // Best-effort: on failure, allow a later retry rather than getting stuck.
        pending.forEach((id) => autoVerifyAttempted.current.delete(id))
      }
    }, 700)
    return () => clearTimeout(timer)
  }, [jobs, applyVerifications])

  const handleVerifyJob = async (id, { force = false } = {}) => {
    try {
      const result = await verifyJob(id, { force })
      applyVerification(id, result)
      const messages = {
        live: 'Posting confirmed live',
        expired: 'Posting is no longer open',
        unreachable: 'Could not reach the source',
      }
      showToast(messages[result.status] || 'Re-checked posting', result.status === 'expired' ? 'error' : 'success')
      return result
    } catch {
      showToast('Could not verify this posting', 'error')
      return null
    }
  }

  const handleToggleFavorite = (id) => {
    const removed = prefs.toggleFavorite(id)
    showToast(removed ? 'Removed from saved jobs' : 'Saved job')
  }

  const handleToggleHidden = (id) => {
    const removed = prefs.toggleHidden(id)
    showToast(removed ? 'Job shown' : 'Job hidden')
  }

  const handleClearHidden = () => {
    prefs.clearHidden()
    showToast('Hidden jobs shown')
  }
  const handleToggleTheme = () => setTheme((prev) => (prev === 'light' ? 'dark' : 'light'))

  const handleSaveSearch = async (name, params) => {
    try {
      await savedSearches.add(name, params)
      showToast('Search saved', 'success')
    } catch {
      showToast('Could not save search', 'error')
    }
  }

  const handleRunSaved = (entry) => {
    setInitialParams(entry.params)
    handleSearch(entry.params)
  }

  const handleDeleteSaved = async (id) => {
    try {
      await savedSearches.remove(id)
      showToast('Saved search deleted')
    } catch {
      showToast('Could not delete saved search', 'error')
    }
  }

  const handleUpdateSaved = async (id, patch) => {
    try {
      await savedSearches.update(id, patch)
      if (patch.alert_enabled !== undefined) {
        showToast(patch.alert_enabled ? 'Email alerts on' : 'Email alerts off', 'success')
      }
    } catch {
      showToast('Could not update saved search', 'error')
    }
  }

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
      <header className="app-header">
        <div className="header-content">
          <div className="brand-lockup">
            <span className="brand-mark" aria-hidden="true">CS</span>
            <div>
              <span className="eyebrow">Contract intelligence</span>
              <h1>Contract Scout</h1>
            </div>
          </div>
          <div className="header-actions">
            <AuthBar />
            <ThemeToggle theme={theme} onToggle={handleToggleTheme} />
          </div>
        </div>
        <div className="hero-content">
          <p>Find high-quality remote US contract roles without searching every job board yourself.</p>
          <div className="hero-stats" aria-label="Contract Scout status">
            <span><strong>{total || jobStats?.count || 0}</strong> opportunities</span>
            <span><strong>{sources.filter((source) => source.configured !== false).length}</strong> sources ready</span>
            <span><strong>{jobStats?.last_scraped ? formatRelativeTime(jobStats.last_scraped) : 'Not yet'}</strong> refreshed</span>
          </div>
        </div>
      </header>

      <section className="card search-card">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Search workspace</span>
            <h2>Find your next contract</h2>
            <p>Set your target role, rate, and engagement type. We will handle the sources.</p>
          </div>
          <span className="keyboard-hint"><kbd>Ctrl</kbd><kbd>K</kbd> quick focus</span>
        </div>
        <SearchFilters
          onSearch={handleSearch}
          onQueryChange={handleQueryChange}
          onSaveSearch={handleSaveSearch}
          loading={loading}
          sources={sources}
          companies={companies}
          initialParams={initialParams}
          recentSearches={recentSearches}
        />
      </section>

      <SavedSearchesPanel
        searches={savedSearches.searches}
        supportsAlerts={savedSearches.supportsAlerts}
        onRun={handleRunSaved}
        onDelete={handleDeleteSaved}
        onUpdate={handleUpdateSaved}
      />

      <ScrapeHealthPanel />

      <section className="card">
        <div className="results-header">
          <div className="results-title">
            <h2>
              {viewMode === 'favorites'
                ? `Saved jobs (${visibleJobs.length})`
                : `Jobs (${visibleJobs.length}${total > visibleJobs.length ? ` of ${total}` : ''})`}
            </h2>
            {jobStats?.last_scraped && (
              <span className="last-scraped" title={new Date(jobStats.last_scraped).toLocaleString()}>
                Last scraped {formatRelativeTime(jobStats.last_scraped)}
              </span>
            )}
          </div>
          <div className="results-actions">
            <div className="view-tabs" role="group" aria-label="Job view">
              <button
                type="button"
                className={`view-tab${viewMode === 'all' ? ' view-tab--active' : ''}`}
                onClick={() => setViewMode('all')}
                aria-pressed={viewMode === 'all'}
              >
                All
              </button>
              <button
                type="button"
                className={`view-tab${viewMode === 'favorites' ? ' view-tab--active' : ''}`}
                onClick={() => setViewMode('favorites')}
                aria-pressed={viewMode === 'favorites'}
              >
                Saved {favoriteSet.size > 0 && <span>{favoriteSet.size}</span>}
              </button>
            </div>
            {riskyIds.size > 0 && (
              <button
                type="button"
                onClick={() => setHideRisky((prev) => !prev)}
                className={`quality-filter-button${hideRisky ? ' quality-filter-button--active' : ''}`}
                aria-pressed={hideRisky}
                title="Hide listings flagged as likely expired, not truly remote, or low quality"
              >
                {hideRisky ? `Showing vetted only` : `Hide ${riskyIds.size} flagged`}
              </button>
            )}
            {prefs.hidden.length > 0 && (
              <button onClick={handleClearHidden} className="clear-hidden-button">
                Show {prefs.hidden.length} hidden
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
        {viewMode === 'all' && total > 0 && (
          <div className="results-progress" aria-label={`Loaded ${jobs.length} of ${total} jobs`}>
            <div className="results-progress__track">
              <span style={{ width: `${Math.min((jobs.length / total) * 100, 100)}%` }} />
            </div>
            <span>{jobs.length} loaded</span>
          </div>
        )}
        {visibleJobs.length > 0 && <PayInsights jobs={visibleJobs} />}
        {viewMode === 'all' && !loading && (hiddenCount > 0 || includeIneligible) && (
          <div className="guardrail-banner" role="status" data-testid="guardrail-banner">
            <span className="guardrail-banner__text">
              {includeIneligible
                ? 'Showing roles not confirmed remote or US-eligible.'
                : `${hiddenCount} more ${hiddenCount === 1 ? 'match is' : 'matches are'} hidden — not confirmed remote or US-eligible.`}
            </span>
            <button
              type="button"
              className="guardrail-banner__action"
              onClick={handleToggleIneligible}
              data-testid="guardrail-toggle"
            >
              {includeIneligible ? 'Hide them' : 'Show these too'}
            </button>
          </div>
        )}
        <JobList
          jobs={jobs}
          loading={loading}
          loadingMore={loadingMore}
          error={error}
          hasMore={hasMore}
          onLoadMore={handleLoadMore}
          onSelectJob={handleSelectJob}
          onRetry={handleRetry}
          favorites={prefs.favorites}
          hidden={prefs.hidden}
          viewed={prefs.viewed}
          lastVisit={lastVisit}
          viewMode={viewMode}
          hideRisky={hideRisky}
          onToggleFavorite={handleToggleFavorite}
          onToggleHidden={handleToggleHidden}
        />
      </section>

      <JobDetail
        job={selectedJob}
        loading={selectedJobLoading}
        error={selectedJobError}
        onClose={handleCloseDetail}
        onVerify={handleVerifyJob}
      />

      <ToastContainer toasts={toasts} onClose={onCloseToast} />

      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {announcement}
      </div>
    </div>
  )
}

function App() {
  const [toasts, setToasts] = useState([])
  const toastIdRef = useRef(0)

  const showToast = useCallback((message, type = 'info') => {
    const id = ++toastIdRef.current
    setToasts((prev) => [...prev, { id, message, type }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id))
    }, 3000)
  }, [])

  const handleCloseToast = useCallback((id) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id))
  }, [])

  return (
    <AuthProvider onNotify={showToast}>
      <AppContent toasts={toasts} showToast={showToast} onCloseToast={handleCloseToast} />
    </AuthProvider>
  )
}

export default App
