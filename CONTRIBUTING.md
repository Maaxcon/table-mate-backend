## AI Workflow (Speckit)

### Prerequisites
- Clone repo
- Install project dependencies
- Install and enable Speckit integration in your IDE/CLI

### Branching
- Base branch: `dev`
- Work branches: `feature/*`, `fix/*`, `chore/*`
- Open PR back to `dev`

### Feature Flow
1. `speckit-specify "feature description"`
2. `speckit-plan`
3. `speckit-tasks`
4. `speckit-implement` (or implement manually by `tasks.md`)

### What must be committed
- `AGENTS.md`
- `.specify/**`
- `specs/NNN-feature-name/**` (spec/plan/tasks + related artifacts)
- Code changes + tests + migrations (if any)


