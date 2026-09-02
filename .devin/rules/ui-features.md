---
trigger: always_on
---

# Contract Scout — UI Feature Backlog

This file is the persistent memory for UI improvements in the Contract Scout project. Refer to it when planning frontend work.

## Implemented

- **URL-synced filters + recent searches** — `SearchFilters` and `App` now read/write the URL query string and persist/recall recent searches in `localStorage`.
- **Pagination / "Load more"** — `App` and `JobList` use the backend `limit`/`offset` params with a "Load more" button.
- **Job detail modal** — `JobCard` is clickable and opens a `JobDetail` modal with full description, badges, and apply link.
- **Save/hide jobs** — `JobCard` has Save and Hide actions; saved/hidden IDs are persisted in `localStorage` and filterable via a view mode.
- **Export and copy search link** — Results header has CSV, JSON, and copy-link buttons.
- **Dark mode + responsive tweaks** — Theme toggle persists in localStorage; dark mode overrides core colors and the mobile layout wraps better.

## Current state snapshot

- Stack: React 18 + Vite, plain CSS, no UI library.
- Components: `App`, `SearchFilters`, `JobList`, `JobCard`, `api`.
- Existing UI: search form with filters, skeleton loaders, job cards, expand/collapse description, refresh button.
- Backend capabilities already available and not yet used by the UI:
  - `GET /api/v1/jobs/{job_id}` — individual job detail.
  - `POST /api/v1/jobs/filter` — full filter payload.
  - `DELETE /api/v1/jobs` — clear all stored jobs.
  - `limit` and `offset` query params for pagination.
  - `company` filter query param.

## Proposed UI features

### Search & filters
1. **URL-synced filters** — persist active filters in the URL query string so searches are shareable and survive reloads.
2. **Recent searches** — store last N searches in `localStorage` and surface them below the search form.
3. **Saved searches** (localStorage first) — let users save and re-run filter combinations; later migrate to backend once auth exists.
4. **Search-as-you-type with debounce** for the query input, using `GET /api/v1/jobs`.
5. **Active filter chips** — show a row of removable chips for each applied filter with one-click removal.
6. **Company filter / autocomplete** — use the existing `company` query param; build a client-side autocomplete from results.
7. **Negative keywords** — allow excluding terms (e.g. `-senior`) in the query box.

### Results browsing
8. **Pagination or infinite scroll** — use the existing `limit`/`offset` parameters.
9. **Sort control** — sort by date posted, min/max pay, relevance.
10. **Job detail view** — open a modal or route using `GET /api/v1/jobs/{job_id}`.
11. **Favorite/save jobs** — store IDs in `localStorage`; add a favorites filter.
12. **Hide/mark as seen** — let users hide jobs and optionally dim already-viewed listings.
13. **Pay range histogram / insights** — show a small chart of salary distribution across results.
14. **Highlight new jobs** — compare `date_scraped` against last visit and badge fresh listings.

### Data, sharing & persistence
15. **Export results** — download current filtered results as CSV or JSON.
16. **Copy search link** — copy a shareable URL with current filters.
17. **Clear all jobs button** — call `DELETE /api/v1/jobs` with confirmation.
18. **Last-scraped timestamp** — display when the dataset was last refreshed.

### User accounts & roadmap-aligned UI
19. **Authentication UI** — login/signup forms to support saved searches per user.
20. **Saved searches page** — list, edit, delete, and re-run saved searches.
21. **Email alerts settings** — configure alert frequency and filters for saved searches.
22. **Pay normalization display** — show pay converted to a common interval/currency once backend supports it.
23. **Scheduled scraping status** — show scheduler health, next run, and logs once backend supports it.

### Visual & accessibility
24. **Dark mode toggle** — switch between light and dark themes.
25. **Responsive layout** — improve mobile stacking and card widths.
26. **Toast notifications** — confirm actions like “Search saved”, “Favorites cleared”, etc.
27. **Error boundary** — catch React render errors and show a fallback UI.
28. **Empty & error states** — better messages for no results, rate limits, and backend errors.
29. **Keyboard shortcuts** — e.g. `Ctrl/Cmd + K` to focus search, `/` to open filters.
30. **ARIA & focus improvements** — announce loading and results changes to screen readers.

## Suggested implementation order

1. URL-synced filters + recent searches (high impact, no backend changes).
2. Pagination or infinite scroll (uses existing API).
3. Job detail modal (uses existing `GET /api/v1/jobs/{job_id}`).
4. Favorites and hide jobs in `localStorage`.
5. Export results and copy search link.
6. Dark mode and responsive improvements.
7. Saved searches, auth, and alerts once backend support is added.
