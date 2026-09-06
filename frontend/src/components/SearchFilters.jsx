import { useEffect, useRef, useState } from 'react'
import { buildRecentLabel, DEFAULT_FILTER_VALUES } from '../utils/filters'

const HOURS_PER_YEAR = 2080

const DEFAULTS = {
  query: 'software engineer',
  location: 'United States',
  jobType: 'contract',
  employmentType: '',
  minPay: '',
  maxPay: '',
  payUnit: 'hourly',
  source: '',
  company: '',
  sortBy: 'date_posted',
  sortOrder: 'desc',
}

const SORT_OPTIONS = [
  { value: 'date_posted:desc', label: 'Newest first' },
  { value: 'date_posted:asc', label: 'Oldest first' },
  { value: 'annual_max:desc', label: 'Pay (yearly equiv.) – high to low' },
  { value: 'annual_max:asc', label: 'Pay (yearly equiv.) – low to high' },
  { value: 'annual_min:desc', label: 'Pay floor – high to low' },
  { value: 'relevance:desc', label: 'Relevance' },
]

// Convert a stored yearly-USD figure back to a value in the chosen unit.
function fromYearly(yearly, unit) {
  if (yearly == null) return ''
  return unit === 'hourly' ? Math.round(yearly / HOURS_PER_YEAR) : Math.round(yearly)
}

// Convert a typed value in the chosen unit to a yearly-USD figure.
function toYearly(value, unit) {
  if (!value) return undefined
  const n = parseFloat(value)
  if (Number.isNaN(n)) return undefined
  return unit === 'hourly' ? n * HOURS_PER_YEAR : n
}

function paramsToState(params) {
  const payUnit = params.pay_unit ?? DEFAULTS.payUnit
  return {
    query: params.query ?? DEFAULTS.query,
    location: params.location ?? DEFAULTS.location,
    jobType: params.job_type ?? DEFAULTS.jobType,
    employmentType: params.employment_type ?? DEFAULTS.employmentType,
    minPay: fromYearly(params.min_yearly, payUnit),
    maxPay: fromYearly(params.max_yearly, payUnit),
    payUnit,
    source: params.source ?? DEFAULTS.source,
    company: params.company ?? DEFAULTS.company,
    sortBy: params.sort_by ?? DEFAULTS.sortBy,
    sortOrder: params.sort_order ?? DEFAULTS.sortOrder,
  }
}

function formatCompact(n) {
  if (n == null) return ''
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: 'compact',
    maximumFractionDigits: 0,
  }).format(n)
}

function SearchFilters({
  onSearch,
  onQueryChange,
  onSaveSearch,
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
  const [payUnit, setPayUnit] = useState(DEFAULTS.payUnit)
  const [source, setSource] = useState(DEFAULTS.source)
  const [company, setCompany] = useState(DEFAULTS.company)
  const [sortBy, setSortBy] = useState(DEFAULTS.sortBy)
  const [sortOrder, setSortOrder] = useState(DEFAULTS.sortOrder)
  const [savedName, setSavedName] = useState('')
  const [showCompanySuggestions, setShowCompanySuggestions] = useState(false)
  const [highlightedCompany, setHighlightedCompany] = useState(-1)
  const companyInputRef = useRef(null)
  const queryInputRef = useRef(null)
  const queryDebounceRef = useRef(null)

  useEffect(() => {
    const next = paramsToState(initialParams ?? DEFAULT_FILTER_VALUES)
    setQuery(next.query)
    setLocation(next.location)
    setJobType(next.jobType)
    setEmploymentType(next.employmentType)
    setMinPay(next.minPay)
    setMaxPay(next.maxPay)
    setPayUnit(next.payUnit)
    setSource(next.source)
    setCompany(next.company)
    setSortBy(next.sortBy)
    setSortOrder(next.sortOrder)
  }, [initialParams])

  useEffect(() => {
    return () => {
      if (queryDebounceRef.current) {
        clearTimeout(queryDebounceRef.current)
      }
    }
  }, [])

  useEffect(() => {
    const handleKeyDown = (e) => {
      const active = document.activeElement
      if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.tagName === 'SELECT' || active.isContentEditable)) {
        return
      }

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        queryInputRef.current?.focus()
      } else if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault()
        queryInputRef.current?.focus()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  const buildParams = () => ({
    query,
    location,
    is_remote: true,
    job_type: jobType,
    employment_type: employmentType || undefined,
    min_yearly: toYearly(minPay, payUnit),
    max_yearly: toYearly(maxPay, payUnit),
    pay_unit: payUnit,
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
    setPayUnit(next.payUnit)
    setSource(next.source)
    setCompany(next.company)
    setSortBy(next.sortBy)
    setSortOrder(next.sortOrder)
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    cancelQueryDebounce()
    onSearch(buildParams())
  }

  const handleReset = () => {
    cancelQueryDebounce()
    applyState(DEFAULT_FILTER_VALUES)
    onSearch({ ...DEFAULT_FILTER_VALUES, query: DEFAULTS.query, location: DEFAULTS.location, job_type: DEFAULTS.jobType })
  }

  const handleRecentClick = (entry) => {
    cancelQueryDebounce()
    applyState(entry.params)
    onSearch(entry.params)
  }

  const handleSaveSearch = () => {
    const params = buildParams()
    const name = savedName.trim() || buildRecentLabel(params)
    onSaveSearch?.(name, params)
    setSavedName('')
  }

  const handleClearFilter = (filter) => {
    cancelQueryDebounce()
    onSearch({ ...buildParams(), ...filter.clear })
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

  const cancelQueryDebounce = () => {
    if (queryDebounceRef.current) {
      clearTimeout(queryDebounceRef.current)
      queryDebounceRef.current = null
    }
  }

  const sortValue = `${sortBy}:${sortOrder}`
  const sortLabel = SORT_OPTIONS.find((option) => option.value === sortValue)?.label || sortValue

  const unitLabel = payUnit === 'hourly' ? '/hr' : '/yr'
  // Live hint that shows how the typed floor is compared on a yearly basis.
  const minYearly = toYearly(minPay, payUnit)
  const payHint =
    payUnit === 'hourly' && minYearly
      ? `≈ ${formatCompact(minYearly)}/yr — salaried roles are matched against this yearly figure`
      : 'Contract rates and full-time salaries are compared on one yearly scale'

  const activeFilters = [
    query !== DEFAULTS.query && { key: 'query', label: query || 'No search term', clear: { query: DEFAULTS.query } },
    location !== DEFAULTS.location && { key: 'location', label: location || 'Any location', clear: { location: DEFAULTS.location } },
    jobType !== DEFAULTS.jobType && { key: 'job_type', label: jobType, clear: { job_type: DEFAULTS.jobType } },
    employmentType && { key: 'employment_type', label: employmentType.toUpperCase(), clear: { employment_type: undefined } },
    minPay && { key: 'min_yearly', label: `min $${minPay}${unitLabel}`, clear: { min_yearly: undefined } },
    maxPay && { key: 'max_yearly', label: `max $${maxPay}${unitLabel}`, clear: { max_yearly: undefined } },
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
        <label className="field-grow">
          Search
          <input
            ref={queryInputRef}
            id="search-query"
            type="text"
            value={query}
            onChange={(e) => {
              const value = e.target.value
              setQuery(value)
              cancelQueryDebounce()
              queryDebounceRef.current = setTimeout(() => {
                onQueryChange?.({ ...buildParams(), query: value })
              }, 300)
            }}
            placeholder="e.g. senior react engineer  (-junior to exclude)"
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
        <div className="pay-field">
          <span className="pay-field__legend">Pay floor</span>
          <div className="pay-field__row">
            <div className="pay-input-group">
              <span className="pay-input-group__prefix">$</span>
              <input
                type="number"
                value={minPay}
                onChange={(e) => setMinPay(e.target.value)}
                placeholder={payUnit === 'hourly' ? '100' : '200000'}
                aria-label="Minimum pay"
              />
            </div>
            <span className="pay-field__to">to</span>
            <div className="pay-input-group">
              <span className="pay-input-group__prefix">$</span>
              <input
                type="number"
                value={maxPay}
                onChange={(e) => setMaxPay(e.target.value)}
                placeholder="max"
                aria-label="Maximum pay"
              />
            </div>
            <div className="unit-toggle" role="group" aria-label="Pay unit">
              <button
                type="button"
                className={payUnit === 'hourly' ? 'unit-toggle__btn unit-toggle__btn--active' : 'unit-toggle__btn'}
                onClick={() => setPayUnit('hourly')}
                aria-pressed={payUnit === 'hourly'}
              >
                / hr
              </button>
              <button
                type="button"
                className={payUnit === 'yearly' ? 'unit-toggle__btn unit-toggle__btn--active' : 'unit-toggle__btn'}
                onClick={() => setPayUnit('yearly')}
                aria-pressed={payUnit === 'yearly'}
              >
                / yr
              </button>
            </div>
          </div>
          <span className="pay-field__hint">{payHint}</span>
        </div>
        <label>
          Source
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">Default sources</option>
            {sources.map((s) => (
              <option key={s.id} value={s.id} disabled={s.configured === false}>
                {s.label}{s.configured === false ? ' (configure first)' : ''}
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
            aria-expanded={showCompanySuggestions && companySuggestions.length > 0}
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
        <div className="save-search">
          <input
            type="text"
            value={savedName}
            onChange={(e) => setSavedName(e.target.value)}
            placeholder="Name this search"
            aria-label="Search name"
            disabled={loading}
          />
          <button type="button" className="reset" onClick={handleSaveSearch} disabled={loading}>
            Save
          </button>
        </div>
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
          <button type="button" className="clear-filters-button" onClick={handleReset} disabled={loading}>
            Clear all
          </button>
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
    </form>
  )
}

export default SearchFilters
