# AGENTS.md

## Mission
Build reliable backend features fast, with clear specs and predictable delivery.

## Required Context
- Always read the current feature artifacts first:
- `specs/<feature>/spec.md`
- `specs/<feature>/plan.md`
- `specs/<feature>/tasks.md`
- If no feature exists yet, start from `speckit-specify`.

## Workflow (Mandatory)
1. `speckit-specify "<feature description>"`
2. `speckit-plan`
3. `speckit-tasks`
4. `speckit-implement` (or implement manually from `tasks.md`)

## Project Standards
- Stack: Python 3.12, Django, DRF, PostgreSQL.
- Lint: `flake8`
- Security checks: `bandit`, `safety`
- Default API access: authenticated endpoints (`IsAuthenticated`).

## Git Rules
- Base branch: `dev`
- Work branches: `feature/*`, `fix/*`, `chore/*`
- Use Conventional Commits: `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`
- Open PR to `dev` with passing CI.

## Commit Scope
- Must commit shared workflow artifacts:
- `AGENTS.md`
- `.specify/**`
- `specs/**` for the active feature
- Plus code/tests/migrations related to the feature.

## Definition of Done
- Feature behavior works as specified.
- `spec/plan/tasks` are up to date.
- Lint, security checks, and tests pass.
- PR is ready for review.
