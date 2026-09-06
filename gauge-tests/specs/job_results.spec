# Job result deduplication

These checks exercise the same paginated API used by the results UI.

## Current results are unique

* Fetch all active job results
* Every result has a unique id
* No results share a normalized company and title
* API total count matches the returned results
