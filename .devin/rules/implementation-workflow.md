---
trigger: always_on
---

# Implementation workflow

- Test every new implementation before considering it complete. Run the most relevant focused tests first, then the appropriate broader test, lint, type-check, or build commands for the affected area.
- Do not report an implementation as complete when verification is failing. Fix regressions or clearly report blockers.
- At the end of every implementation session, review all changes and create a Git commit when there are changes to commit.
- Never skip verification or the final commit unless the user explicitly requests it or a blocker prevents it.
- Do not push commits unless the user explicitly asks.
