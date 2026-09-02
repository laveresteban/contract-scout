export function formatCurrency(amount, currency) {
  if (amount == null) return ''
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency || 'USD',
    maximumFractionDigits: 0,
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

export function formatPay(job) {
  const parts = []
  if (job.min_amount != null) parts.push(formatCurrency(job.min_amount, job.currency))
  if (job.max_amount != null) parts.push(formatCurrency(job.max_amount, job.currency))
  if (!parts.length) return null
  let label = parts.join(' – ')
  if (job.interval) label += ` / ${job.interval}`
  return label
}
