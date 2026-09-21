# Saved-search alert email

Exercises the API that lets a saved search carry an explicit delivery address
(so an anonymous `ip:` search can be emailed, and an authenticated one can
override its account email). Runs against the backend directly.

## An alert email round-trips and is validated

* Create a saved search with alert email "alerts@example.com"
* The saved search stores alert email "alerts@example.com"
* Clearing the alert email removes it
* A malformed alert email is rejected
* Delete the saved search
