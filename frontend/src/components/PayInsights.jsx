import { formatCurrency } from '../utils/format'

const BUCKET_COUNT = 5

function PayInsights({ jobs }) {
  const jobsWithPay = jobs.filter(
    (job) => job.normalized_min_yearly != null || job.normalized_max_yearly != null
  )

  if (jobsWithPay.length === 0) return null

  const minimums = jobsWithPay.map((job) => job.normalized_min_yearly ?? job.normalized_max_yearly)
  const maximums = jobsWithPay.map((job) => job.normalized_max_yearly ?? job.normalized_min_yearly)
  const values = jobsWithPay.map((job) => {
    const minimum = job.normalized_min_yearly ?? job.normalized_max_yearly
    const maximum = job.normalized_max_yearly ?? job.normalized_min_yearly
    return (minimum + maximum) / 2
  })
  const currency = 'USD'
  const coverage = Math.round((jobsWithPay.length / jobs.length) * 100)
  const min = Math.min(...minimums)
  const max = Math.max(...maximums)
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
        <div>
          <span className="eyebrow">Market snapshot</span>
          <h3>Annual pay insights</h3>
        </div>
        <span className="pay-insights__count">{jobsWithPay.length} jobs with disclosed pay</span>
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
        <div className="pay-stat">
          <span className="pay-stat__label">Pay coverage</span>
          <span className="pay-stat__value">{coverage}%</span>
        </div>
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
