## Contributor Workflow (After Pull)

### 1. Pull Latest Changes
1. `git checkout dev`
2. `git pull`

### 2. Prepare Local Environment
1. Install backend dependencies: `pip install -r requirements/dev.txt`
2. Speckit is already initialized in this repo. Do not run `specify init .` again.
3. Use one Speckit execution mode:
- Codex mode (recommended): `$speckit-specify`, `$speckit-plan`, `$speckit-tasks`, `$speckit-implement`
- CLI mode: verify command access with `uvx --from git+https://github.com/github/spec-kit.git specify --version`

### 3. Create a Working Branch
1. Use one of the approved scope prefixes:
- `foundation/<short-name>`
- `auth/<short-name>`
- `menu/<short-name>`
- `reservations/<short-name>`
- `cart/<short-name>`
- `staff-ops/<short-name>`
- `payment/<short-name>`
- `polish/<short-name>`
2. Example: `git checkout -b foundation/backend-settings-fix`

### 4. Feature Delivery Flow (Mandatory)
1. `speckit-specify "feature description"`
2. `speckit-plan`
3. `speckit-tasks`
4. `speckit-implement` or implement manually from `tasks.md`

If you use Codex chat commands, use:
`$speckit-specify`, `$speckit-plan`, `$speckit-tasks`, `$speckit-implement`

- `speckit-specify`: Describes what the feature should do.
- `speckit-plan`: Reviews architecture and implementation approach.
- `speckit-tasks`: Breaks the plan into actionable tasks.
- `speckit-implement`: Executes implementation from approved tasks.

### 5. CLI Alternative (If you do not use IDE commands)
1. `uvx --from git+https://github.com/github/spec-kit.git specify workflow info speckit`
2. `uvx --from git+https://github.com/github/spec-kit.git specify workflow run speckit -i spec="feature description" -i integration=codex -i scope=full`
3. Complete workflow gates when prompted (`review-spec`, `review-plan`).
4. Continue implementation manually from generated `spec.md`, `plan.md`, and `tasks.md` when needed.
5. Note: `specify run ...` is not supported in current CLI versions.

### 6. What Must Be Committed
- `AGENTS.md` when project-level agent rules are changed
- `.specify/**` when workflow templates/rules are changed
- `specs/NNN-feature-name/**` for the active feature
- Feature code changes
- Tests and migrations when applicable

### 7. Testing Approach

We follow a **real-objects, behaviour-level** testing strategy:

- **Fixtures over mocks.** Use `factory_boy` + `conftest.py` shared fixtures (`user_factory(role=...)`, `api(role=...)`). Reserve `unittest.mock` for project boundaries (external APIs, Redis, etc.).
- **Parametrised matrices.** Permission tests use `@pytest.mark.parametrize` to cover all role × permission combinations instead of writing individual test methods per class.
- **End-to-end via APIClient.** Exception handler tests raise exceptions inside real `APIView` subclasses and assert the response — no mocking of `exception_handler`.
- **AnonymousUser.** Always include at least one test for unauthenticated/`None` user paths.

Run tests with `pytest --reuse-db` locally for speed; CI uses fresh Postgres via the service container (already configured in `.github/`).

### 8. Quality Gates Before PR
1. Lint must pass: `ruff check apps core common manage.py`
2. Security checks must pass: `bandit -r apps core common manage.py`
3. Tests must pass: `pytest --reuse-db`
4. Open PR to `dev`
5. PR requires at least 1 approval and passing CI

### 9. Commit Message Format
- Use Conventional Commits: `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`
