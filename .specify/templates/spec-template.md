# Feature Specification: [FEATURE NAME]

**Feature Branch**: `[###-feature-name]`
**Created**: [DATE]
**Status**: Draft
**Input**: User description: "$ARGUMENTS"

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.

  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - [Brief Title] (Priority: P1)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently - e.g., "Can be fully tested by [specific action] and delivers [specific value]"]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]
2. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

### User Story 2 - [Brief Title] (Priority: P2)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

### User Story 3 - [Brief Title] (Priority: P3)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right edge cases.
-->

- What happens when [boundary condition]?
- How does system handle [error scenario]?

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: System MUST [specific capability, e.g., "allow users to create accounts"]
- **FR-002**: System MUST [specific capability, e.g., "validate email addresses"]
- **FR-003**: Users MUST be able to [key interaction, e.g., "reset their password"]
- **FR-004**: System MUST [data requirement, e.g., "persist user preferences"]
- **FR-005**: System MUST [behavior, e.g., "log all security events"]

*Example of marking unclear requirements:*

- **FR-006**: System MUST authenticate users via [NEEDS CLARIFICATION: auth method not specified - email/password, SSO, OAuth?]
- **FR-007**: System MUST retain user data for [NEEDS CLARIFICATION: retention period not specified]

### Canonical Contract Impact *(mandatory when shared entities are affected)*

<!--
  Document whether the feature changes canonical entity shape/semantics.
  Include backward compatibility and rollout expectations for clients.
-->

- **Impacted Entities**: [Restaurant/Table/Order/OrderItem/Ticket/Session/Staff or N/A]
- **Contract Delta**: [added/changed/removed fields with compatibility plan]
- **Backend Source of Truth Rule**: [how backend-authoritative state is enforced]

### Role Access Matrix *(mandatory when feature touches role-based behavior)*

<!--
  Define capabilities per affected role and explicitly list restricted actions.
  Backend enforcement is mandatory; UI hiding alone is insufficient.
-->

- **Cook**: [allowed capabilities]
- **Cook Restricted**: [explicitly denied capabilities]
- **Waiter**: [allowed capabilities]
- **Waiter Restricted**: [explicitly denied capabilities]
- **Manager**: [allowed capabilities]
- **Manager Restricted**: [explicitly denied capabilities]
- **Admin**: [allowed capabilities]
- **Admin Restricted**: [explicitly denied capabilities]

### Realtime Event Contracts *(mandatory when feature has live state)*

<!--
  For each event, define source, audience, channel, payload fields, and
  schema_version behavior. Live state must be delivered by WebSocket;
  REST should create/mutate state only.
-->

- **Event**: `[EVENT_NAME]`
- **Audience**: [role/session scope]
- **Transport**: [websocket channel/path]
- **Payload**: [field list]
- **schema_version**: [version value and compatibility notes]
- **Unknown Version Handling**: [client ignore strategy and fallback behavior]

### Event Delivery Guarantees *(mandatory when feature has live state)*

<!--
  Define live delivery semantics. Constitution baseline is at-least-once
  delivery with reconnect replay for the session window.
-->

- **Delivery Guarantee**: [at-least-once / N/A with rationale]
- **Replay Window**: [how disconnected clients recover missed events]
- **Idempotency Strategy**: [how duplicate event handling is made safe]

### Transaction & State Authority *(mandatory when payments/voids/session totals are involved)*

<!--
  Define which transitions are backend-authoritative and what must be atomic.
  If partial failure is possible, document rollback contract.
-->

- **Authoritative Transition**: [e.g., payment status update via webhook]
- **Atomic Group**: [list of state changes/events that commit together]
- **Rollback Rule**: [all-or-nothing behavior]
- **No-Optimistic-Truth Rule**: [how clients avoid authoritative local transitions]

### Session Lifecycle Rules *(mandatory when table/session occupancy is affected)*

<!--
  Sessions must have explicit open and close triggers. If snapshots are written
  at close, define immutable analytics contract and live-state discard behavior.
-->

- **Open Trigger(s)**: [manual order start, prepaid webhook, etc.]
- **Close Trigger(s)**: [explicit close-table action only / other]
- **Close Snapshot Contract**: [fields persisted for analytics]

### Layout Versioning Contract *(mandatory when floor plan/editor is affected)*

<!--
  Layout publications should create immutable versions and maintain stable table
  identity references.
-->

- **Version Model**: [immutable versioned layouts / other]
- **ID Stability Rule**: [table ID behavior across versions]
- **Update Delivery Path**: [backend-initiated event and client apply behavior]

### Frontend Surface Contract *(mandatory when frontend behavior is in scope)*

<!--
  Frontend is role-composed. Inaccessible role routes/components must not be
  mounted. If floor plan is touched, define live patching path.
-->

- **Role Tree Mounting Rule**: [which role trees mount and which do not]
- **Floor Plan State Source**: [backend-pushed status only / N/A]
- **Spatial Editor Separation**: [separate route context behavior / N/A]

### Offline & Reconnection Contract *(mandatory when frontend behavior is in scope)*

<!--
  There is no offline write mode. Disconnection should block writes and require
  state refresh before writes resume after reconnect.
-->

- **Disconnect UX**: [persistent error state behavior]
- **Write Blocking Rule**: [which actions are disabled while disconnected]
- **Reconnect Recovery**: [state refresh before write re-enable]

### Destructive Action Confirmation Contract *(mandatory when irreversible actions are in scope)*

<!--
  Void, cancel reservation, and close table require explicit consequence-facing
  confirmation before execution.
-->

- **Impacted Actions**: [void/cancel reservation/close table or N/A]
- **Required Fields**: [reason code, is_wasted, totals, served-item count, etc.]
- **Dismiss/Cancel Behavior**: [outside tap and cancel semantics]

### Theme & Token Contract *(mandatory when frontend behavior is in scope)*

<!--
  Status colors are semantic tokens, not inline component values. Theme changes
  should be immediate and non-flashing.
-->

- **Semantic Token Rules**: [status and table-state token mapping]
- **Theme Modes**: [light/dark support and contrast requirements]
- **Switch Behavior**: [instant apply without flash]

### Floor Plan Performance Contract *(mandatory when floor plan rendering is in scope)*

- **Render Budget**: [<=100ms from WebSocket state delivery on target hardware]
- **Verification Method**: [instrumentation/profiling approach]
- **Network-on-Render Rule**: [confirm no per-table render fetches]

### Financial Data Boundary *(mandatory when billing/revenue/reporting is affected)*

<!--
  Financial records are API read-only from external callers. Specify internal
  write paths and any derived metric computation rules.
-->

- **External Write Access**: [forbidden/allowed with rationale]
- **Internal Write Sources**: [payment webhook, void transaction, session close]
- **Derived Metric Rule**: [e.g., AVG PREP from raw cycle records, query-time]
- **Indexing Requirement**: [restaurant + session timestamp index strategy]

### Key Entities *(include if feature involves data)*

- **[Entity 1]**: [What it represents, key attributes without implementation]
- **[Entity 2]**: [What it represents, relationships to other entities]

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: [Measurable metric, e.g., "Users can complete account creation in under 2 minutes"]
- **SC-002**: [Measurable metric, e.g., "System handles 1000 concurrent users without degradation"]
- **SC-003**: [User satisfaction metric, e.g., "90% of users successfully complete primary task on first attempt"]
- **SC-004**: [Business metric, e.g., "Reduce support tickets related to [X] by 50%"]

## Assumptions

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right assumptions based on reasonable defaults
  chosen when the feature description did not specify certain details.
-->

- [Assumption about target users, e.g., "Users have stable internet connectivity"]
- [Assumption about scope boundaries, e.g., "Mobile support is out of scope for v1"]
- [Assumption about data/environment, e.g., "Existing authentication system will be reused"]
- [Dependency on existing system/service, e.g., "Requires access to the existing user profile API"]
