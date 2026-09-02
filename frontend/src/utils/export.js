function escapeCsv(value) {
  const str = value == null ? '' : String(value)
  if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
    return `"${str.replace(/"/g, '""')}"`
  }
  return str
}

export function jobsToCsv(jobs) {
  const columns = [
    'title',
    'company',
    'location',
    'site',
    'job_type',
    'employment_type',
    'interval',
    'min_amount',
    'max_amount',
    'currency',
    'date_posted',
    'job_url',
    'job_url_direct',
    'description',
  ]
  const header = columns.join(',')
  const rows = jobs.map((job) =>
    columns
      .map((col) => {
        const value = job[col]
        if (col === 'description') return escapeCsv(stripHtml(value))
        return escapeCsv(value)
      })
      .join(',')
  )
  return [header, ...rows].join('\n')
}

function stripHtml(html) {
  if (!html) return ''
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

export function downloadFile(content, filename, type) {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
