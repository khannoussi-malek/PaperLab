## What this changes

<!-- One or two sentences. Link the issue if there is one. -->

## How you checked it

<!-- The commands you ran and what they said. For retrieval or chunking changes, the eval numbers
     before and after (`docker compose exec api python -m evals.run`). For UI changes, a screenshot
     in both light and dark. -->

- [ ] `cd backend && uv run pytest && uv run ruff check .`
- [ ] `cd frontend && npx tsc -b && npm test`
- [ ] E2E, if this touches a user flow
- [ ] A test that fails without this change

## Anything reviewers should know

<!-- Trade-offs, things you weren't sure about, follow-ups you deliberately left out. -->
