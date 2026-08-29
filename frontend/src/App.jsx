import { useState } from 'react'
import SearchFilters from './components/SearchFilters'
import JobList from './components/JobList'
import { listJobs, scrapeJobs } from './api'

function App() {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [lastSearch, setLastSearch] = useState({})

  const handleSearch = async (params) => {
    setLoading(true)
    setError(null)
    setLastSearch(params)
    try {
      await scrapeJobs({ ...params, results_wanted: 25 })
      const fetched = await listJobs({
        q: params.query,
        is_remote: true,
        is_us: true,
        job_type: params.job_type,
        employment_type: params.employment_type,
        min_pay: params.min_pay,
        max_pay: params.max_pay,
        pay_interval: params.pay_interval,
        limit: 100,
      })
      setJobs(fetched)
    } catch (err) {
      setError(err.message || 'Something went wrong.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <header>
        <h1>Contract Scout</h1>
        <p>Remote US contract jobs for software engineers and tech professionals.</p>
      </header>

      <section className="card">
        <SearchFilters onSearch={handleSearch} loading={loading} />
      </section>

      <section className="card">
        <div className="results-header">
          <h2>Jobs ({jobs.length})</h2>
          {lastSearch.query && !loading && (
            <button onClick={() => handleSearch(lastSearch)}>Refresh</button>
          )}
        </div>
        <JobList jobs={jobs} loading={loading} error={error} />
      </section>
    </div>
  )
}

export default App
