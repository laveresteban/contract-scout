# Background re-verification

The background loop re-checks active jobs whose verify verdict is missing or
stale. This drives the same work through its manual trigger endpoint, so the
count is deterministic (it's the number of jobs processed, regardless of what
each source returns).

## The manual trigger re-checks a bounded batch

* Re-verify stale jobs with limit "2" treating everything as stale
* The re-verification checked "2" jobs
