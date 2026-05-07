## Contributor Workflow (After Pull)

### 1. Pull Latest Changes
1. `git checkout dev`
2. `git pull`

### 2. Prepare Local Environment
1. Install backend dependencies: `pip install -r requirements/dev.txt`
2. Speckit is already initialized in this repo. Do not run `specify init .` again.
3. Use one Speckit execution mode:
4. IDE mode: use your Speckit-enabled agent integration.
5. CLI mode: verify command access with `uv tool install specify-cli --from git+https://github.com/github/spec-kit.git`

### 3. Create a Working Branch
1. `git checkout -b feature/<short-name>`
2. For bugfixes use `fix/<short-name>`
3. For maintenance/docs use `chore/<short-name>`

### 4. Feature Delivery Flow (Mandatory)
1. `speckit-specify "feature description"`
2. `speckit-plan`
3. `speckit-tasks`
4. `speckit-implement` or implement manually from `tasks.md`

if you use codex  command - $speckit-specify, $speckit-plan, $speckit-implement

/speckit.specify: Describing exactly what a module should do (e.g., "Create a data processing utility for employee records").
/speckit.plan: Reviewing the architectural plan before any code is written. This ensures the agent is correctly planning the React hooks or Django DRF endpoints you actually need.
/speckit.tasks: Breaking the plan down into actionable steps.
/speckit.implement: Executing the code generation.

### 5. CLI Alternative (If you do not use IDE commands)
1. `uvx --from git+https://github.com/github/spec-kit.git specify run speckit.specify "feature description"`
2. `uvx --from git+https://github.com/github/spec-kit.git specify run speckit.plan "feature description"`
3. `uvx --from git+https://github.com/github/spec-kit.git specify run speckit.tasks "feature description"`
4. `uvx --from git+https://github.com/github/spec-kit.git specify run speckit.implement "feature description"`

### 6. What Must Be Committed
- `AGENTS.md` when project-level agent rules are changed
- `.specify/**` when workflow templates/rules are changed
- `specs/NNN-feature-name/**` for the active feature
- Feature code changes
- Tests and migrations when applicable

### 7. Quality Gates Before PR
1. Lint must pass: `flake8`
2. Security checks must pass: `bandit`, `safety`
3. Tests must pass
4. Open PR to `dev`
5. PR requires at least 1 approval and passing CI

### 8. Commit Message Format
- Use Conventional Commits: `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`
