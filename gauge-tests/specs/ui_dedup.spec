# De-duplicated results in the browser

Drives the real React UI with Selenium to confirm the fix end-to-end: the same
role scraped by several boards collapses to a single card, and the results list
isn't shortened by client-side dedup papering over server duplicates.

Prerequisites: the backend is running (seeded with `--with-duplicates`, then
`python -m app.backfill_dedup`) and the frontend dev server is up. See
`gauge-tests/README.md`.

## The same role from several boards shows once

* Open the Contract Scout app
* Search the UI for "Backend Engineer"
* No two visible job cards are duplicates
* The role "Senior Backend Engineer" appears exactly once
