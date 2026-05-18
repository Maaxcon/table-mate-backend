# AGENTS.md

## Mission
Build reliable backend features fast, with clear specs and predictable delivery.

## Required Context
- Always read the current feature artifacts first:
- `specs/<feature>/spec.md`
- `specs/<feature>/plan.md`
- `specs/<feature>/tasks.md`
- `.specify/memory/constitution.md`
- If no feature exists yet, start from `speckit-specify`.

## Workflow (Mandatory)
1. `speckit-specify "<feature description>"`
2. `speckit-plan`
3. `speckit-tasks`
4. `speckit-implement` (or implement manually from `tasks.md`)

### Codex Command Mapping
- In Codex chat mode, use:
- `$speckit-specify`
- `$speckit-plan`
- `$speckit-tasks`
- `$speckit-implement`

## Project Standards
- Stack: Python 3.12, Django 5+, DRF, PostgreSQL, Redis, Channels.
- Auth: JWT (`djangorestframework-simplejwt`) + Google OAuth exchange.
- Architecture rule: Skinny Views, Fat Services, Selectors pattern.
- Lint: `flake8`
- Security checks: `bandit`, `safety`
- Default API permission class: `IsAuthenticated`. Public-read endpoints (menu categories/items) are documented exceptions per FR-016.

## Git Rules
- Base branch: `dev`
- Work branches must use scope prefixes:
- `foundation/*`
- `auth/*`
- `menu/*`
- `reservations/*`
- `cart/*`
- `staff-ops/*`
- `payment/*`
- `polish/*`
- If a feature branch already exists for the same scope, continue work there (do not create duplicate branch lines).
- Use Conventional Commits: `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`
- Open PR to `dev` with passing CI.

## Commit Scope
- Must commit shared workflow artifacts:
- `AGENTS.md`
- `.specify/memory/constitution.md` when changed
- `.specify/**`
- `specs/**` for the active feature
- Plus code/tests/migrations related to the feature.

## Definition of Done
- Feature behavior works as specified.
- `constitution/spec/plan/tasks` are up to date.
- Lint, security checks, and tests pass.
- PR is ready for review.
