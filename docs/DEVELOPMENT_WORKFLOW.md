
# WalkLah Development Workflow

## Branches

- main: stable, tested version
- integration/mvp: combined frontend and backend
- feat/backend-routing: CS A backend work
- feat/frontend-map: CS B frontend work

## Ownership

CS A:
- backend/
- backend tests

CS B:
- frontend/

Shared:
- docs/
- README.md
- .gitignore

API changes require agreement from both developers.

## Before starting work

1. Save your current work.
2. Check your current branch with git branch --show-current.
3. Fetch the latest changes using git fetch origin.
4. Pull the latest version of your own branch.
5. Do not start from an outdated integration branch.

## Before committing

1. Run relevant tests.
2. Run git status.
3. Review git diff.
4. Add only files related to your task.
5. Commit with a descriptive message.
6. Push your branch.

## Integration

1. Open a pull request into integration/mvp.
2. Ask the other teammate to review.
3. Resolve conflicts before merging.
4. Run frontend build and backend tests.
5. Test the complete user flow.
6. Merge integration/mvp into main only when stable.

## Rules

- Never force-push shared branches.
- Never commit .env, credentials, or local virtual environments.
- Do not edit the other developer's files without discussing it.
- Do not change the API contract unilaterally.
- Prefer small commits that do one thing.