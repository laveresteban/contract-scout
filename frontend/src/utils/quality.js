// Client-side job-quality evaluation.
//
// Job boards are noisy: postings tagged "remote" that are actually on-site,
// listings that were filled weeks ago, and evergreen "talent pipeline" posts
// that aren't a real open role. The backend can't catch all of these, so we
// score every job here and surface the risks on the card before the user
// wastes an application on a dead or misleading posting.

import { stripHtml } from './format'

const DAY_MS = 24 * 60 * 60 * 1000

// Signals in the body copy that contradict a "remote" tag.
const ONSITE_RE =
  /\b(on[-\s]?site|in[-\s]?office|in[-\s]?person|hybrid|must relocate|relocation (is )?(required|available)|report to (our|the|a)[^.]{0,30}office|days? (per week |a week )?in (the |our )?office|commute|onsite)\b/i

// Phrases that require living in a specific place — remote-in-name-only.
const LOCATION_LOCK_RE =
  /\b(must (be|reside|live|be located|be based)|required to (live|reside|be located)|based in|located in|local candidates|no relocation|within commuting distance)\b/i

// Evergreen / pipeline postings that aren't a specific vacancy.
const PIPELINE_RE =
  /\b(talent (community|network|pool|pipeline)|general application|evergreen|future (opportunities|openings|roles)|expression of interest|join our (talent|network)|multiple (positions|openings|locations)|various (positions|locations)|pipeline requisition|we are always (hiring|looking))\b/i

// Placeholder / undisclosed employers, common on scraped aggregator feeds.
const VAGUE_COMPANY_RE =
  /^(confidential|undisclosed|company confidential|private|n\/?a|staffing|recruiting|recruiter|multiple)/i

function ageInDays(dateString) {
  if (!dateString) return null
  const posted = new Date(dateString).getTime()
  if (Number.isNaN(posted)) return null
  return Math.floor((Date.now() - posted) / DAY_MS)
}

/**
 * Evaluate a job and return a trust assessment.
 *
 * @returns {{
 *   tier: 'trusted' | 'review' | 'risky',
 *   score: number,            // 0-100
 *   flags: Array<{ id: string, level: 'warn' | 'caution' | 'info', label: string, detail: string }>,
 *   remoteConfidence: 'confirmed' | 'unverified' | null,
 * }}
 */
export function evaluateJob(job) {
  let flags = []
  let score = 100

  const text = stripHtml(job?.description || '')
  const haystack = `${job?.title || ''} ${job?.location || ''} ${text}`
  const age = ageInDays(job?.date_posted)

  // --- Freshness: has the role likely already been filled? -------------------
  // Tracked separately so a backend verification (which is ground truth) can
  // refund these guesses instead of double-counting them.
  let freshnessPenalty = 0
  if (age == null) {
    freshnessPenalty = 8
    flags.push({
      id: 'no-date',
      level: 'info',
      label: 'Undated',
      detail: 'No posting date — freshness can’t be confirmed.',
    })
  } else if (age > 60) {
    freshnessPenalty = 45
    flags.push({
      id: 'expired',
      level: 'warn',
      label: 'Likely expired',
      detail: `Posted ${age} days ago — roles this old are usually filled or closed.`,
    })
  } else if (age > 30) {
    freshnessPenalty = 18
    flags.push({
      id: 'stale',
      level: 'caution',
      label: 'Aging',
      detail: `Posted ${age} days ago — may no longer be open.`,
    })
  }
  score -= freshnessPenalty

  // --- Remote reality check --------------------------------------------------
  let remoteConfidence = null
  if (job?.is_remote) {
    const onsite = ONSITE_RE.test(text)
    const locationLock = LOCATION_LOCK_RE.test(text)
    if (onsite || locationLock) {
      remoteConfidence = 'unverified'
      score -= 28
      flags.push({
        id: 'remote-mismatch',
        level: 'warn',
        label: 'Remote unverified',
        detail: onsite
          ? 'Tagged remote, but the description mentions on-site, hybrid, or office work.'
          : 'Tagged remote, but the description requires living in a specific location.',
      })
    } else {
      remoteConfidence = 'confirmed'
    }
  }

  // --- US eligibility --------------------------------------------------------
  if (job?.eligibility === 'non_us') {
    score -= 30
    flags.push({
      id: 'non-us',
      level: 'warn',
      label: 'Non-US',
      detail: 'This role appears to require eligibility outside the US.',
    })
  } else if (job?.eligibility === 'unknown') {
    score -= 6
    flags.push({
      id: 'elig-unknown',
      level: 'info',
      label: 'Eligibility unclear',
      detail: 'Work authorization / location eligibility isn’t stated.',
    })
  }

  // --- Ghost / pipeline roles: "the role doesn't exist" ----------------------
  if (PIPELINE_RE.test(haystack)) {
    score -= 25
    flags.push({
      id: 'pipeline',
      level: 'caution',
      label: 'Pipeline post',
      detail: 'Reads like a talent-pool or evergreen listing, not one specific open role.',
    })
  }

  // --- Thin / missing description --------------------------------------------
  if (!text) {
    score -= 30
    flags.push({
      id: 'no-description',
      level: 'warn',
      label: 'No description',
      detail: 'The listing has no job description to review.',
    })
  } else if (text.length < 200) {
    score -= 14
    flags.push({
      id: 'thin-description',
      level: 'caution',
      label: 'Thin details',
      detail: 'Very short description — hard to tell if the role is real or complete.',
    })
  }

  // --- Placeholder employer --------------------------------------------------
  if (!job?.company || VAGUE_COMPANY_RE.test(String(job.company).trim())) {
    score -= 12
    flags.push({
      id: 'vague-company',
      level: 'caution',
      label: 'Undisclosed employer',
      detail: 'No clear hiring company — often a staffing repost or lead-gen listing.',
    })
  }

  // --- Missing apply link ----------------------------------------------------
  if (!job?.job_url_direct && !job?.job_url) {
    score -= 20
    flags.push({
      id: 'no-link',
      level: 'warn',
      label: 'No apply link',
      detail: 'No link to the original posting — can’t verify or apply.',
    })
  }

  // --- Backend verification overrides the heuristic guesses ------------------
  // A real re-fetch of the source is higher-confidence than anything we can
  // infer from stale scrape fields, so it supersedes the freshness guesses.
  let verified = false
  switch (job?.verify_status) {
    case 'expired':
      verified = true
      score = Math.min(score, 20)
      flags = flags.filter((f) => f.id !== 'expired' && f.id !== 'stale' && f.id !== 'no-date')
      flags.unshift({
        id: 'verified-expired',
        level: 'warn',
        label: 'Confirmed closed',
        detail: job.verify_detail || 'We re-checked the source — this posting is no longer open.',
      })
      break
    case 'live':
      verified = true
      // We actually confirmed it's open, so refund the freshness guesses
      // (drop the flags AND the score they cost) and add a confidence bump.
      flags = flags.filter((f) => f.id !== 'expired' && f.id !== 'stale' && f.id !== 'no-date')
      score = Math.min(100, score + freshnessPenalty + 15)
      flags.unshift({
        id: 'verified-live',
        level: 'info',
        label: 'Verified live',
        detail: job.verify_detail || 'We re-checked the source — this posting is still open.',
      })
      break
    case 'unreachable':
      flags.push({
        id: 'verify-unreachable',
        level: 'info',
        label: 'Couldn’t re-check',
        detail: job.verify_detail || 'The source couldn’t be reached to confirm this listing.',
      })
      break
    default:
      break
  }

  score = Math.max(0, Math.min(100, score))
  const tier = score >= 80 ? 'trusted' : score >= 55 ? 'review' : 'risky'

  return { tier, score, flags, remoteConfidence, verified, verifyStatus: job?.verify_status || 'unverified' }
}

const TIER_LABELS = {
  trusted: 'Looks solid',
  review: 'Worth a look',
  risky: 'Verify before applying',
}

export function tierLabel(tier) {
  return TIER_LABELS[tier] || ''
}

// The single most important warning to surface, if any.
export function primaryWarning(assessment) {
  if (!assessment?.flags?.length) return null
  return (
    assessment.flags.find((f) => f.level === 'warn') ||
    assessment.flags.find((f) => f.level === 'caution') ||
    null
  )
}
