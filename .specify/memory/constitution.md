<!--
Sync Impact Report
- Version change: template -> 1.0.0
- Modified principles:
  - [PRINCIPLE_1_NAME] -> I. Architectural Philosophy (Domain-Driven Design)
  - [PRINCIPLE_2_NAME] -> II. Tech Stack & Environment
  - [PRINCIPLE_3_NAME] -> III. Data Model Standards
  - [PRINCIPLE_4_NAME] -> IV. Coding & Quality Standards
  - [PRINCIPLE_5_NAME] -> V. Pragmatic Delivery Workflow
- Added sections:
  - VI. Git Workflow & Version Control
  - VII. Auth & Permissions
- Removed sections:
  - None
- Templates requiring updates:
  - ✅ .specify/templates/plan-template.md (no change required; Constitution Check remains generic)
  - ✅ .specify/templates/spec-template.md (no change required)
  - ✅ .specify/templates/tasks-template.md (no change required)
- Deferred TODOs:
  - None
-->

# Table-mate Backend Constitution

## Core Principles

### I. Architectural Philosophy (Domain-Driven Design)
- Skinny Views, Fat Services: API Views (`views.py`, `api/*`) only route,
  validate input, and shape responses.
- All business logic, orchestration, and domain rules MUST live in
  `services.py`.
- Complex ORM queries (`annotate`, `select_related`, `prefetch_related`,
  aggregations) MUST live in `selectors.py`.
- SOLID principles are mandatory; modules MUST be loosely coupled and easily
  testable.

### II. Tech Stack & Environment
- Core stack: Python 3.12, Django 5+, Django REST Framework.
- Primary database: PostgreSQL; `JSONB` is allowed for flexible domain payloads
  when justified.
- Real-time capabilities: Redis + Django Channels (`asgi.py`) for
  websocket-driven flows.
- Local development MUST run via Docker and `docker-compose`.
- Settings MUST remain environment-split (`base`, `local`, `production`).

### III. Data Model Standards
- Domain models MUST use shared base mixins from `common/`:
  - `UUIDMixin` for UUID primary keys.
  - `TimestampMixin` for `created_at` and `updated_at`.
- Circular imports between `apps/` are prohibited.
- Cross-app dependencies MUST go through stable service/selectors boundaries.

### IV. Coding & Quality Standards
- Public service and selector functions MUST have explicit type hints for
  arguments and return values.
- Linting baseline is `flake8` (must pass in CI).
- Security gates in CI are mandatory: `bandit` and dependency checks
  (`safety`).
- Business/domain errors MUST use custom exception classes in `common/`.
- Target code style: readable, consistent lines around 88-100 chars where
  practical.

### V. Pragmatic Delivery Workflow
- Prefer simple, reliable implementations over premature abstraction.
- Every change MUST be CI-ready: lint + security checks + tests.
- "Done" means: working behavior, clear boundaries, and green CI.

### VI. Git Workflow & Version Control
- Use short-lived working branches (`feature/*`, `fix/*`, `chore/*`) and merge
  through Pull Requests.
- Conventional Commits are required (`feat:`, `fix:`, `refactor:`, `docs:`,
  `chore:` and similar typed prefixes).
- Each Pull Request requires at least one approval and passing CI before merge.
- If commit hooks are added, they MUST be Python-native (`pre-commit`);
  Node/Husky is out of scope.

### VII. Auth & Permissions (amended)

- API endpoints are closed by default via DRF IsAuthenticated.
- Authentication: JWT via djangorestframework-simplejwt.
  This is an explicit architecture decision for this project
  because the frontend is a React SPA with Google OAuth
  and WebSocket connections.
- Flow:
    Frontend sends Google OAuth token
    → POST /api/auth/google/
    → Backend verifies with Google
    → Returns JWT access + refresh tokens
    → Frontend stores in Redux + localStorage
    → Attaches JWT as Authorization: Bearer <token>
      on every request via Axios interceptor
- Role-based access (Guest, AuthUser, Admin, Waiter, Hostess)
  MUST be implemented through custom DRF permission classes.

## Operational Constraints

- Keep app boundaries explicit under `apps/` and avoid hidden cross-app writes.
- For asynchronous or realtime flows, define failure modes and retry behavior.
- New dependencies require justification in feature planning artifacts.

## Development Workflow

- Feature execution flow is mandatory: `specify -> plan -> tasks -> implement`.
- Pull Requests MUST include:
  - scope summary,
  - verification steps,
  - migration notes (if DB changes exist).
- Changes that affect auth, permissions, or contracts MUST include integration
  tests before merge.

## Governance

- This constitution overrides ad-hoc local conventions.
- Amendments require Pull Request discussion and explicit team approval.
- Versioning policy:
  - MAJOR: incompatible governance changes,
  - MINOR: new principle/section,
  - PATCH: clarification-only updates.
- Compliance is checked during planning, task generation, review, and CI.

**Version**: 1.0.0 | **Ratified**: 2026-05-06 | **Last Amended**: 2026-05-06
