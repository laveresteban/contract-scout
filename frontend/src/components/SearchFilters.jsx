import { useState } from 'react'

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

function SearchFilters({ onSearch, loading, sources = [] }) {
  const [query, setQuery] = useState(DEFAULTS.query)
  const [location, setLocation] = useState(DEFAULTS.location)
  const [jobType, setJobType] = useState(DEFAULTS.jobType)
  const [employmentType, setEmploymentType] = useState(DEFAULTS.employmentType)
  const [minPay, setMinPay] = useState(DEFAULTS.minPay)
  const [maxPay, setMaxPay] = useState(DEFAULTS.maxPay)
  const [payInterval, setPayInterval] = useState(DEFAULTS.payInterval)
  const [source, setSource] = useState(DEFAULTS.source)

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

  const handleSubmit = (e) => {
    e.preventDefault()
    onSearch(buildParams())
  }

  const handleReset = () => {
    setQuery(DEFAULTS.query)
    setLocation(DEFAULTS.location)
    setJobType(DEFAULTS.jobType)
    setEmploymentType(DEFAULTS.employmentType)
    setMinPay(DEFAULTS.minPay)
    setMaxPay(DEFAULTS.maxPay)
    setPayInterval(DEFAULTS.payInterval)
    setSource(DEFAULTS.source)
    onSearch({
      query: DEFAULTS.query,
      location: DEFAULTS.location,
      is_remote: true,
      job_type: DEFAULTS.jobType,
      employment_type: undefined,
      min_pay: undefined,
      max_pay: undefined,
      pay_interval: undefined,
      source: undefined,
    })
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
    </form>
  )
}

export default SearchFilters
