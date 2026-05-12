# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]
**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]  
**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]  
**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]  
**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]  
**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]
**Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app or NEEDS CLARIFICATION]  
**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]  
**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]  
**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Rule | Status | Evidence in Plan |
|------|------|--------|------------------|
| C1 | Right role, right moment, zero ambiguity is preserved | [PASS/FAIL] | [Describe role-targeted state delivery and ambiguity controls] |
| C2 | Canonical shared entity contracts are preserved (Restaurant/Table/Order/OrderItem/Ticket/Session/Staff) | [PASS/FAIL/N/A] | [List contract impacts, compatibility approach, and source-of-truth ownership] |
| C3 | Role access matrix is backend-enforced and structurally reflected in clients | [PASS/FAIL/N/A] | [List allowed/denied actions per affected role] |
| C4 | Live state uses WebSocket-only typed/versioned events; REST is create/mutate only | [PASS/FAIL/N/A] | [List event catalog entries, `schema_version`, and transport paths] |
| C5 | Delivery guarantee supports at-least-once semantics and reconnect replay | [PASS/FAIL/N/A] | [Describe replay window, idempotency strategy, and ordering constraints] |
| C6 | Payment confirmation is webhook-only with signature validation | [PASS/FAIL/N/A] | [Describe blocked alternate paths and atomic post-webhook transitions] |
| C7 | Void flow is atomic with explicit rollback and audit data | [PASS/FAIL/N/A] | [Describe transaction scope, failure behavior, and emitted events] |
| C8 | Session lifecycle is explicit (open triggers, human close, immutable snapshot) | [PASS/FAIL/N/A] | [Describe open/close triggers and analytics snapshot contract] |
| C9 | Kitchen queue ordering preserves injection-time priority | [PASS/FAIL/N/A] | [Describe queue key/order semantics and grouped-view ordering] |
| C10 | Auth uses role-scoped tokens with immediate invalidation on role change | [PASS/FAIL/N/A] | [Describe token claims, runtime permission mapping, invalidation path] |
| C11 | Floor layout updates are immutable/versioned with stable table IDs and backend-driven delivery | [PASS/FAIL/N/A] | [Describe layout versioning model and update event flow] |
| C12 | Financial records are externally read-only; AVG PREP is query-time from raw cycle data | [PASS/FAIL/N/A] | [Describe write boundaries and metric computation/query indexing] |
| C13 | Frontend-only constraints are respected when frontend scope exists (role trees, offline error state, destructive confirmations, floor plan <=100ms paint) | [PASS/FAIL/N/A] | [List UI architecture, error handling, and perf validation evidence] |
| C14 | Mandatory backend stack and architecture are respected (Python/Django/DRF/PostgreSQL/Redis/Channels + Skinny Views/Fat Services/Selectors) | [PASS/FAIL] | [List concrete modules/services/selectors ownership] |

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
