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
  const now = new Date()
  const seconds = Math.floor((now - d) / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)
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

export function formatPay(job) {
  const parts = []
  if (job.min_amount != null) parts.push(formatCurrency(job.min_amount, job.currency))
  if (job.max_amount != null) parts.push(formatCurrency(job.max_amount, job.currency))
  if (!parts.length) return null
  let label = parts.join(' – ')
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
  return `${formatCompactUSD(max ?? min)}/yr`
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
