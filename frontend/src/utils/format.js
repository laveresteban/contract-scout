export function formatCurrency(amount, currency) {
  if (amount == null) return ''
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency || 'USD',
    maximumFractionDigits: 0,
  }).format(amount)
}

// Compact USD like $208K or $1.2M, for the yearly-equivalent comp figure.
export function formatCompactUSD(amount) {
  if (amount == null) return ''
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(amount)
}

export function stripHtml(html) {
  if (!html) return ''
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

export function formatDate(dateString) {
  if (!dateString) return null
  const d = new Date(dateString)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function formatRelativeTime(dateString) {
  if (!dateString) return null
  const d = new Date(dateString)
  if (Number.isNaN(d.getTime())) return null
  const deltaSeconds = Math.floor((d - new Date()) / 1000)
  const future = deltaSeconds > 0
  const seconds = Math.abs(deltaSeconds)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)
  if (future) {
    if (seconds < 60) return 'in less than a minute'
    if (minutes < 60) return `in ${minutes}m`
    if (hours < 24) return `in ${hours}h`
    if (days < 7) return `in ${days}d`
    return formatDate(dateString)
  }
  if (seconds < 60) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  if (hours < 24) return `${hours}h ago`
  if (days < 7) return `${days}d ago`
  return formatDate(dateString)
}

const INTERVAL_SUFFIX = {
  hourly: '/hr',
  weekly: '/wk',
  daily: '/day',
  monthly: '/mo',
  yearly: '/yr',
}

const INTERVAL_NOUN = {
  hourly: 'Hourly rate',
  daily: 'Daily rate',
  weekly: 'Weekly rate',
  monthly: 'Monthly rate',
  yearly: 'Annual salary',
}

// Human label for a raw pay interval, e.g. "Hourly rate".
export function intervalLabel(interval) {
  return INTERVAL_NOUN[interval] || 'Pay rate'
}

export function formatPay(job) {
  const minimum = job.min_amount != null ? formatCurrency(job.min_amount, job.currency) : null
  const maximum = job.max_amount != null ? formatCurrency(job.max_amount, job.currency) : null
  if (!minimum && !maximum) return null
  let label = minimum && maximum ? (minimum === maximum ? minimum : `${minimum} – ${maximum}`) : minimum ? `From ${minimum}` : `Up to ${maximum}`
  if (job.interval) label += ` ${INTERVAL_SUFFIX[job.interval] || `/ ${job.interval}`}`
  return label
}

// Yearly-USD-equivalent comp, always shown when the backend could normalize it.
// This is the figure that puts $100/hr contracts and $150k/yr salaries on one
// scale, so it headlines every card regardless of the source interval.
export function formatAnnualPay(job) {
  const min = job.normalized_min_yearly
  const max = job.normalized_max_yearly
  if (min == null && max == null) return null
  if (min != null && max != null && min !== max) {
    return `${formatCompactUSD(min)} – ${formatCompactUSD(max)}/yr`
  }
  if (min != null && max == null) return `From ${formatCompactUSD(min)}/yr`
  if (max != null && min == null) return `Up to ${formatCompactUSD(max)}/yr`
  return `${formatCompactUSD(max ?? min)}/yr`
}

// One place that resolves every pay figure a card or the modal needs, so the
// two views can't drift apart. `annual` headlines; `raw` is the source-interval
// rate, shown only when it says something the yearly figure doesn't.
export function getPayDisplay(job) {
  const annual = formatAnnualPay(job)
  const raw = formatPay(job)
  const rawIsDistinct = Boolean(raw && job.interval && job.interval !== 'yearly')
  return {
    hasPay: Boolean(annual || raw),
    annual,
    raw,
    rawIsDistinct,
    intervalLabel: intervalLabel(job.interval),
  }
}

const ELIGIBILITY_LABELS = {
  explicit_us: 'US listed',
  remote_us_assumed: 'Remote · US assumed',
  non_us: 'Non-US',
  unknown: 'Eligibility unknown',
}

export function eligibilityLabel(job) {
  return ELIGIBILITY_LABELS[job.eligibility] || null
}
