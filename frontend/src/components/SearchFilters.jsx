import { useState } from 'react'

function SearchFilters({ onSearch, loading }) {
  const [query, setQuery] = useState('software engineer contract')
  const [location, setLocation] = useState('United States')
  const [jobType, setJobType] = useState('contract')
  const [employmentType, setEmploymentType] = useState('')
  const [minPay, setMinPay] = useState('')
  const [maxPay, setMaxPay] = useState('')
  const [payInterval, setPayInterval] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    onSearch({
      query,
      location,
      is_remote: true,
      job_type: jobType,
      employment_type: employmentType || undefined,
      min_pay: minPay ? parseFloat(minPay) : undefined,
      max_pay: maxPay ? parseFloat(maxPay) : undefined,
      pay_interval: payInterval || undefined,
    })
  }

  return (
    <form className="search-form" onSubmit={handleSubmit}>
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
      <button type="submit" disabled={loading}>
        {loading ? 'Searching…' : 'Search'}
      </button>
    </form>
  )
}

export default SearchFilters
