import { formatCurrency } from '../utils/format'

const BUCKET_COUNT = 5

function PayInsights({ jobs }) {
  const jobsWithPay = jobs.filter((job) => job.min_amount != null || job.max_amount != null)

  if (jobsWithPay.length === 0) return null

  const values = jobsWithPay.map((job) => job.max_amount ?? job.min_amount)
  const currency = jobsWithPay.find((job) => job.currency)?.currency || 'USD'
  const intervals = {}
  jobsWithPay.forEach((job) => {
    if (job.interval) {
      intervals[job.interval] = (intervals[job.interval] || 0) + 1
    }
  })
  const primaryInterval = Object.entries(intervals).sort((a, b) => b[1] - a[1])[0]?.[0]

  const min = Math.min(...values)
  const max = Math.max(...values)
  const avg = values.reduce((a, b) => a + b, 0) / values.length

  const range = max - min || 1
  const bucketSize = range / BUCKET_COUNT
  const buckets = Array(BUCKET_COUNT).fill(0)
  values.forEach((value) => {
    const index = Math.min(Math.floor((value - min) / bucketSize), BUCKET_COUNT - 1)
    buckets[index] += 1
  })

  const maxCount = Math.max(...buckets)

  const bucketLabel = (index) => {
    const from = min + index * bucketSize
    const to = from + bucketSize
    return `${formatCurrency(from, currency)} – ${formatCurrency(to, currency)}`
  }

  return (
    <div className="pay-insights">
      <div className="pay-insights__header">
        <h3>Pay insights</h3>
        <span className="pay-insights__count">{jobsWithPay.length} jobs with pay</span>
      </div>
      <div className="pay-insights__stats">
        <div className="pay-stat">
          <span className="pay-stat__label">Range</span>
          <span className="pay-stat__value">
            {formatCurrency(min, currency)} – {formatCurrency(max, currency)}
          </span>
        </div>
        <div className="pay-stat">
          <span className="pay-stat__label">Average</span>
          <span className="pay-stat__value">{formatCurrency(avg, currency)}</span>
        </div>
        {primaryInterval && (
          <div className="pay-stat">
            <span className="pay-stat__label">Interval</span>
            <span className="pay-stat__value">{primaryInterval}</span>
          </div>
        )}
      </div>
      <div className="pay-histogram" role="img" aria-label="Pay range histogram">
        {buckets.map((count, index) => (
          <div key={index} className="pay-histogram__row">
            <span className="pay-histogram__label">{bucketLabel(index)}</span>
            <div className="pay-histogram__bar-track">
              <div
                className="pay-histogram__bar"
                style={{ width: `${maxCount ? (count / maxCount) * 100 : 0}%` }}
              />
            </div>
            <span className="pay-histogram__count">{count}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default PayInsights
