import { useEffect, useState } from 'react'
import { DEFAULT_FILTER_VALUES } from '../utils/filters'

const DEFAULTS = {
  query: 'software engineer',
  location: 'United States',
  jobType: 'contract',
  employmentType: '',
  minPay: '',
  maxPay: '',
  payInterval: '',
  source: '',
}

function paramsToState(params) {
  return {
    query: params.query ?? DEFAULTS.query,
    location: params.location ?? DEFAULTS.location,
    jobType: params.job_type ?? DEFAULTS.jobType,
    employmentType: params.employment_type ?? DEFAULTS.employmentType,
    minPay: params.min_pay ?? DEFAULTS.minPay,
    maxPay: params.max_pay ?? DEFAULTS.maxPay,
    payInterval: params.pay_interval ?? DEFAULTS.payInterval,
    source: params.source ?? DEFAULTS.source,
  }
}

function SearchFilters({ onSearch, loading, sources = [], initialParams, recentSearches = [] }) {
  const [query, setQuery] = useState(DEFAULTS.query)
  const [location, setLocation] = useState(DEFAULTS.location)
  const [jobType, setJobType] = useState(DEFAULTS.jobType)
  const [employmentType, setEmploymentType] = useState(DEFAULTS.employmentType)
  const [minPay, setMinPay] = useState(DEFAULTS.minPay)
  const [maxPay, setMaxPay] = useState(DEFAULTS.maxPay)
  const [payInterval, setPayInterval] = useState(DEFAULTS.payInterval)
  const [source, setSource] = useState(DEFAULTS.source)

  useEffect(() => {
    const next = paramsToState(initialParams ?? DEFAULT_FILTER_VALUES)
    setQuery(next.query)
    setLocation(next.location)
    setJobType(next.jobType)
    setEmploymentType(next.employmentType)
    setMinPay(next.minPay)
    setMaxPay(next.maxPay)
    setPayInterval(next.payInterval)
    setSource(next.source)
  }, [initialParams])

  const buildParams = () => ({
    query,
    location,
    is_remote: true,
    job_type: jobType,
    employment_type: employmentType || undefined,
    min_pay: minPay ? parseFloat(minPay) : undefined,
    max_pay: maxPay ? parseFloat(maxPay) : undefined,
    pay_interval: payInterval || undefined,
    source: source || undefined,
  })

  const applyState = (params) => {
    const next = paramsToState(params)
    setQuery(next.query)
    setLocation(next.location)
    setJobType(next.jobType)
    setEmploymentType(next.employmentType)
    setMinPay(next.minPay)
    setMaxPay(next.maxPay)
    setPayInterval(next.payInterval)
    setSource(next.source)
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    onSearch(buildParams())
  }

  const handleReset = () => {
    applyState(DEFAULT_FILTER_VALUES)
    onSearch({
      query: DEFAULT_FILTER_VALUES.query,
      location: DEFAULT_FILTER_VALUES.location,
      is_remote: true,
      job_type: DEFAULT_FILTER_VALUES.job_type,
      employment_type: undefined,
      min_pay: undefined,
      max_pay: undefined,
      pay_interval: undefined,
      source: undefined,
    })
  }

  const handleRecentClick = (entry) => {
    applyState(entry.params)
    onSearch(entry.params)
  }

  return (
    <form className="search-form" onSubmit={handleSubmit}>
      <div className="search-fields">
        <label>
          Search
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. software engineer"
          />
        </label>
        <label>
          Location
          <input
            type="text"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="United States"
          />
        </label>
        <label>
          Job type
          <select value={jobType} onChange={(e) => setJobType(e.target.value)}>
            <option value="contract">Contract</option>
            <option value="fulltime">Full-time</option>
            <option value="parttime">Part-time</option>
            <option value="internship">Internship</option>
          </select>
        </label>
        <label>
          Employment type
          <select value={employmentType} onChange={(e) => setEmploymentType(e.target.value)}>
            <option value="">Any</option>
            <option value="w2">W2</option>
            <option value="1099">1099</option>
            <option value="c2c">C2C</option>
            <option value="contract">Contract</option>
          </select>
        </label>
        <label>
          Min pay
          <input
            type="number"
            value={minPay}
            onChange={(e) => setMinPay(e.target.value)}
            placeholder="0"
          />
        </label>
        <label>
          Max pay
          <input
            type="number"
            value={maxPay}
            onChange={(e) => setMaxPay(e.target.value)}
            placeholder="999"
          />
        </label>
        <label>
          Pay interval
          <select value={payInterval} onChange={(e) => setPayInterval(e.target.value)}>
            <option value="">Any</option>
            <option value="hourly">Hourly</option>
            <option value="yearly">Yearly</option>
            <option value="monthly">Monthly</option>
          </select>
        </label>
        <label>
          Source
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">All sources</option>
            {sources.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="search-actions">
        <button type="submit" disabled={loading}>
          {loading ? 'Searching…' : 'Search'}
        </button>
        <button type="button" className="reset" onClick={handleReset} disabled={loading}>
          Reset
        </button>
      </div>
      {recentSearches.length > 0 && (
        <div className="recent-searches">
          <span className="recent-label">Recent searches</span>
          {recentSearches.map((entry, index) => (
            <button
              key={`${entry.label}-${index}`}
              type="button"
              className="recent-chip"
              onClick={() => handleRecentClick(entry)}
              disabled={loading}
            >
              {entry.label}
            </button>
          ))}
        </div>
      )}
    </form>
  )
}

export default SearchFilters
