import { useEffect, useRef, useState } from 'react'
import { buildRecentLabel, DEFAULT_FILTER_VALUES } from '../utils/filters'
import { addSavedSearch, loadSavedSearches, removeSavedSearch } from '../utils/savedSearches'

const DEFAULTS = {
  query: 'software engineer',
  location: 'United States',
  jobType: 'contract',
  employmentType: '',
  minPay: '',
  maxPay: '',
  payInterval: '',
  source: '',
  company: '',
  sortBy: 'date_posted',
  sortOrder: 'desc',
}

const SORT_OPTIONS = [
  { value: 'date_posted:desc', label: 'Date posted – newest' },
  { value: 'date_posted:asc', label: 'Date posted – oldest' },
  { value: 'min_pay:asc', label: 'Pay (min) – low to high' },
  { value: 'min_pay:desc', label: 'Pay (min) – high to low' },
  { value: 'max_pay:asc', label: 'Pay (max) – low to high' },
  { value: 'max_pay:desc', label: 'Pay (max) – high to low' },
  { value: 'relevance:desc', label: 'Relevance' },
]

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
    company: params.company ?? DEFAULTS.company,
    sortBy: params.sort_by ?? DEFAULTS.sortBy,
    sortOrder: params.sort_order ?? DEFAULTS.sortOrder,
  }
}

function SearchFilters({
  onSearch,
  onShowToast,
  loading,
  sources = [],
  companies = [],
  initialParams,
  recentSearches = [],
}) {
  const [query, setQuery] = useState(DEFAULTS.query)
  const [location, setLocation] = useState(DEFAULTS.location)
  const [jobType, setJobType] = useState(DEFAULTS.jobType)
  const [employmentType, setEmploymentType] = useState(DEFAULTS.employmentType)
  const [minPay, setMinPay] = useState(DEFAULTS.minPay)
  const [maxPay, setMaxPay] = useState(DEFAULTS.maxPay)
  const [payInterval, setPayInterval] = useState(DEFAULTS.payInterval)
  const [source, setSource] = useState(DEFAULTS.source)
  const [company, setCompany] = useState(DEFAULTS.company)
  const [sortBy, setSortBy] = useState(DEFAULTS.sortBy)
  const [sortOrder, setSortOrder] = useState(DEFAULTS.sortOrder)
  const [savedName, setSavedName] = useState('')
  const [savedSearches, setSavedSearches] = useState(() => loadSavedSearches())
  const [showCompanySuggestions, setShowCompanySuggestions] = useState(false)
  const [highlightedCompany, setHighlightedCompany] = useState(-1)
  const companyInputRef = useRef(null)

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
    setCompany(next.company)
    setSortBy(next.sortBy)
    setSortOrder(next.sortOrder)
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
    company: company || undefined,
    sort_by: sortBy,
    sort_order: sortOrder,
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
    setCompany(next.company)
    setSortBy(next.sortBy)
    setSortOrder(next.sortOrder)
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    onSearch(buildParams())
  }

  const handleReset = () => {
    applyState(DEFAULT_FILTER_VALUES)
    onSearch(buildParams())
  }

  const handleRecentClick = (entry) => {
    applyState(entry.params)
    onSearch(entry.params)
  }

  const handleSaveSearch = () => {
    const params = buildParams()
    const name = savedName.trim() || buildRecentLabel(params)
    setSavedSearches((prev) => addSavedSearch(prev, name, params))
    setSavedName('')
    onShowToast('Search saved', 'success')
  }

  const handleClearFilter = (filter) => {
    onSearch({ ...buildParams(), ...filter.clear })
    onShowToast(`Removed ${filter.label}`)
  }

  const handleSavedClick = (entry) => {
    applyState(entry.params)
    onSearch(entry.params)
  }

  const handleDeleteSaved = (id) => {
    setSavedSearches((prev) => removeSavedSearch(prev, id))
  }

  const companySuggestions = company
    ? companies
        .filter((c) => c.toLowerCase().includes(company.toLowerCase()))
        .slice(0, 10)
    : []

  const handleCompanyChange = (e) => {
    setCompany(e.target.value)
    setShowCompanySuggestions(true)
    setHighlightedCompany(-1)
  }

  const selectCompany = (value) => {
    setCompany(value)
    setShowCompanySuggestions(false)
    setHighlightedCompany(-1)
    companyInputRef.current?.focus()
  }

  const handleCompanyBlur = () => {
    // Delay hiding so click events on suggestions can fire first
    setTimeout(() => {
      setShowCompanySuggestions(false)
      setHighlightedCompany(-1)
    }, 150)
  }

  const handleCompanyKeyDown = (e) => {
    if (!showCompanySuggestions || !companySuggestions.length) return

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightedCompany((prev) => (prev + 1) % companySuggestions.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightedCompany((prev) =>
        prev <= 0 ? companySuggestions.length - 1 : prev - 1
      )
    } else if (e.key === 'Enter' && highlightedCompany >= 0) {
      e.preventDefault()
      selectCompany(companySuggestions[highlightedCompany])
    } else if (e.key === 'Escape') {
      setShowCompanySuggestions(false)
      setHighlightedCompany(-1)
    }
  }

  const sortValue = `${sortBy}:${sortOrder}`
  const sortLabel = SORT_OPTIONS.find((option) => option.value === sortValue)?.label || sortValue

  const activeFilters = [
    query !== DEFAULTS.query && { key: 'query', label: query, clear: { query: DEFAULTS.query } },
    location !== DEFAULTS.location && { key: 'location', label: location, clear: { location: DEFAULTS.location } },
    jobType !== DEFAULTS.jobType && { key: 'job_type', label: jobType, clear: { job_type: DEFAULTS.jobType } },
    employmentType && { key: 'employment_type', label: employmentType.toUpperCase(), clear: { employment_type: undefined } },
    minPay && { key: 'min_pay', label: `min $${minPay}`, clear: { min_pay: undefined } },
    maxPay && { key: 'max_pay', label: `max $${maxPay}`, clear: { max_pay: undefined } },
    payInterval && { key: 'pay_interval', label: payInterval, clear: { pay_interval: undefined } },
    source && { key: 'source', label: source, clear: { source: undefined } },
    company && { key: 'company', label: company, clear: { company: undefined } },
    (sortBy !== DEFAULTS.sortBy || sortOrder !== DEFAULTS.sortOrder) && {
      key: 'sort',
      label: `sort: ${sortLabel}`,
      clear: { sort_by: DEFAULTS.sortBy, sort_order: DEFAULTS.sortOrder },
    },
  ].filter(Boolean)

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
        <label className="autocomplete-field">
          Company
          <input
            ref={companyInputRef}
            type="text"
            value={company}
            onChange={handleCompanyChange}
            onFocus={() => setShowCompanySuggestions(true)}
            onBlur={handleCompanyBlur}
            onKeyDown={handleCompanyKeyDown}
            placeholder="e.g. Acme"
            autoComplete="off"
            aria-autocomplete="list"
            aria-controls="company-suggestions"
            aria-activedescendant={
              highlightedCompany >= 0 ? `company-suggestion-${highlightedCompany}` : undefined
            }
          />
          {showCompanySuggestions && companySuggestions.length > 0 && (
            <ul id="company-suggestions" className="autocomplete-list" role="listbox">
              {companySuggestions.map((suggestion, index) => (
                <li
                  key={suggestion}
                  id={`company-suggestion-${index}`}
                  className={`autocomplete-item ${index === highlightedCompany ? 'autocomplete-item--highlighted' : ''}`}
                  role="option"
                  aria-selected={index === highlightedCompany}
                  onMouseDown={(e) => {
                    e.preventDefault()
                    selectCompany(suggestion)
                  }}
                >
                  {suggestion}
                </li>
              ))}
            </ul>
          )}
        </label>
        <label>
          Sort by
          <select
            value={`${sortBy}:${sortOrder}`}
            onChange={(e) => {
              const [nextSortBy, nextSortOrder] = e.target.value.split(':')
              setSortBy(nextSortBy)
              setSortOrder(nextSortOrder)
            }}
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
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
      <div className="save-search">
        <input
          type="text"
          value={savedName}
          onChange={(e) => setSavedName(e.target.value)}
          placeholder="Name this search"
          disabled={loading}
        />
        <button type="button" onClick={handleSaveSearch} disabled={loading}>
          Save search
        </button>
      </div>
      {activeFilters.length > 0 && (
        <div className="active-filters">
          <span className="active-filters__label">Active filters</span>
          {activeFilters.map((filter) => (
            <span key={filter.key} className="active-filter-chip">
              {filter.label}
              <button
                type="button"
                className="active-filter-chip__remove"
                onClick={() => handleClearFilter(filter)}
                aria-label={`Remove ${filter.label}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
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
      {savedSearches.length > 0 && (
        <div className="saved-searches">
          <span className="saved-label">Saved searches</span>
          {savedSearches.map((entry) => (
            <span key={entry.id} className="saved-chip">
              <button
                type="button"
                className="saved-chip__label"
                onClick={() => handleSavedClick(entry)}
                disabled={loading}
              >
                {entry.name}
              </button>
              <button
                type="button"
                className="saved-chip__delete"
                onClick={() => handleDeleteSaved(entry.id)}
                aria-label={`Delete ${entry.name}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </form>
  )
}

export default SearchFilters
