import { useEffect, useState } from 'react'
import SearchFilters from './components/SearchFilters'
import JobList from './components/JobList'
import { listJobs, listSources, scrapeJobs } from './api'
import {
  addRecentSearch,
  deserializeFilters,
  loadRecentSearches,
  serializeFilters,
} from './utils/filters'

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

  useEffect(() => {
    listSources()
      .then((data) => setSources(data))
      .catch(() => setSources([]))

    if (window.location.search) {
      fetchJobs(deserializeFilters(window.location.search))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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
    await fetchJobs(params, { scrape: true })
  }

  const handleLoadMore = () => {
    if (lastSearch && !loadingMore) {
      fetchJobs(lastSearch, { append: true })
    }
  }

  return (
    <div className="container">
      <header>
        <h1>Contract Scout</h1>
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
          <h2>Jobs ({jobs.length})</h2>
          {lastSearch && !loading && (
            <button onClick={() => handleSearch(lastSearch)}>Refresh</button>
          )}
        </div>
        <JobList
          jobs={jobs}
          loading={loading}
          loadingMore={loadingMore}
          error={error}
          hasMore={hasMore}
          onLoadMore={handleLoadMore}
        />
      </section>
    </div>
  )
}

export default App
