# TableMate Platform — Ultimate Architecture & Workflow Document

> Source: converted from `TableMate Platform — Ultimate Architecture & Workflow Document.docx` (kept untracked in repo root). This Markdown file is the canonical version going forward — edit here, not the .docx.

This document outlines the comprehensive end-to-end user journeys for all four primary roles within the TableMate ecosystem: **Client (User), Waiter, Cook, and Admin**. It details the independent workflows and the real-time "digital handshakes" connecting them.

## PART 1: THE CLIENT JOURNEY (Customer Workflow)
*This workflow covers how a guest enters the ecosystem, books a table, manages their profile, and executes prepaid orders.*

### Phase 1: Entry Points & Authorization
The platform provides two distinct entry scenarios based on the user's physical location.

- **Scenario A (In-Venue via QR Code):** The client scans a QR code at the table. The system automatically identifies the restaurant and table. Full platform functionality, including live food ordering, is unlocked.

- **Scenario B (Remote via Link):** The client accesses the platform outside the venue. They manually select a restaurant from the catalog. Live food ordering is blocked; only table booking and reviews are available.

- **Authentication:** Both scenarios lead to a greeting screen offering "Continue as Guest" or "Login / Register." Logging in redirects to Google OAuth for rapid, secure access.

### Phase 2: Table Booking & Reservation Management
1.  **Interactive Spatial Floor Plan:** The user navigates a digital blueprint of the restaurant. The interface prioritizes spatial awareness, displaying tables with clear capacity indicators and real-time color-coded statuses:

    - **Free (White/Outline):** Available for immediate selection or future booking.

    - **Occupied (Solid/Dark):** Currently seating guests (unselectable for immediate walk-ins).

    - **Reserved (Patterned/Gray):** Booked for a specific upcoming time window.

2.  **Dynamic Slot Selection & Confirmation:** Upon tapping a "Free" table, a bottom-sheet modal presents available time slots dynamically filtered against existing reservations and restaurant working hours. The user selects a time and verifies the final booking details (Table ID, Date, Time, Guest Count) via a clear confirmation prompt.

3.  **Success & Lifecycle Management:** Following confirmation, the user is seamlessly routed to the "Active Bookings" tab within their Personal Cabinet. From this hub, they retain full control to modify (adjust time/table) or cancel the reservation. Canceled reservations are gracefully archived in their History tab with a distinct "Canceled" badge for accurate personal tracking.

### Phase 3: The Personal Cabinet (Profile)
The user's central hub for managing their restaurant network activity, built with a 1px-border UI aesthetic and full dark-mode support.

- **Identity & Loyalty:** Displays user name and registration date (e.g., "Member since 2024") and quick access to settings (language, payment methods).

- **Active Bookings (High Priority):** Displays upcoming plans with location (Table 04 / Main Hall), time ("19:00 TODAY"), guest count, and a direct "MODIFY" button.

- **History (Archive):** A chronological feed of past visits showing the date and total bill (e.g., "12 OCT 2024 — €142.00"). Users can tap to view itemized electronic receipts or leave reviews.

- **Global Bottom Navigation:** Allows instant switching between the Menu/Catalog, the Calendar (showing past/future bookings), and the Profile.

### Phase 4: Order Confirmation & Payment (Self-Service)
- **The Checkout Rule:** The *only* way to confirm a client-led order is via online payment. The "Call Waiter to Order" fallback is explicitly removed to prevent abuse and operational bottlenecks.

- **Payment Methods:** The screen offers Apple Pay, Google Pay, or direct Card input.

- **The Trigger:** Upon successful payment, the order status changes to "Paid," and the system automatically injects the ticket into the Kitchen Kanban and alerts the Waiter.

## PART 2: THE WAITER WORKFLOW
*The medium bridging the physical dining room, the digital client requests, and the kitchen.*

### Phase 1: The Booking & Floor Plan (Initial View)
1.  **Dashboard Entry:** The waiter logs in and lands on the **Live Occupancy** floor plan.

2.  **Visual Status Check:** The waiter glides through the map to identify real-time table states:

    - **Free (White/Outline):** Available for walk-ins.

    - **Reserved (Patterned/Gray):** Displays guest name and expected arrival time.

    - **Occupied (Solid/Color):** Displays active session duration and a summary of current order status.

3.  **Table Interaction:** The waiter taps a specific table to open the **Table Detail Overlay**.

### Phase 2: Notification Management (The Pulse)
1.  **Sidebar Alerts:** A persistent notification tab splits into two streams:

    - **Client Stream:** "Table 04 just placed a prepaid order" or "Table 12 is requesting a waiter."

    - **Kitchen Stream:** "Table 05: 2x Steaks are READY."

2.  **Actionable Taps:** Tapping any notification immediately navigates the waiter to that specific table’s order view for verification or service.

### Phase 3: Order Workflow A (Client-Led / Prepaid)
- *Triggered by Client Phase 4.*

1.  **UI Update:** The table on the map pulses to indicate a New Order via client webhook.

2.  **Waiter Review:** The waiter opens the table to see items pre-organized by guest seat. Payment is already marked "Settled."

3.  **Kitchen Handoff:** The waiter performs a final check for conflicting modifiers and taps **"Approve & Fire"** (or the system auto-fires, based on restaurant configuration) to send it to the kitchen.

### Phase 4: Order Workflow B (Waiter-Led / Manual)
1.  **Guest Setup:** Waiter taps an Occupied/Free table, selects the guest count, and the UI creates distinct "Guest Slots."

2.  **Menu & Modifiers:** Waiter taps a menu item. A **Modifier Modal** immediately appears for comments (e.g., "No onions"). The waiter assigns the item to a specific Guest Slot.

3.  **Send to Cook:** After reviewing the draft, tapping **"Send to Kitchen"** injects the ticket into the Kitchen's "Incoming" queue.

### Phase 5: Status Tracking & Fulfillment
1.  **Dish-Level Monitoring:** Inside the table view, items display real-time lifecycle colors syncing from the kitchen: **Gray** (Pending), **Yellow** (In Progress), and **Green** (Ready).

2.  **Service Completion & Reset:** The waiter retrieves "Green" dishes. Once all items are served and the bill is paid, the waiter taps **"Close Table,"** instantly resetting the table to "Free" on the map.

## PART 3: THE KITCHEN WORKFLOW
*The operational engine focused on atomic preparation, batch efficiency, and strict queue ordering.*

### Phase 1: Order Injection (The Digital Handshake)
- *Connects with Waiter Phase 3 & 4.*

1.  **Unified Entry:** Waiter or Prepaid Client tickets appear in the **INCOMING** column, strictly ordered by injection timestamp.

2.  **Cook Claim:** A cook taps the ticket header, moving it to **ACTIVE**. This instantly shifts the Waiter’s UI for that dish from Gray to Yellow (In Progress).

### Phase 2: Atomic Preparation & Progress Tracking
1.  **Incremental Fulfillment:** The cook works through individual items on an Active ticket.

2.  **The Atomic Tap:** The cook finishes one dish (e.g., "1x Wings") and taps that specific block on the Kanban.

3.  **The Pulse:** The waiter's floor plan pulses "Partial Ready", a sidebar alert fires, and the specific item turns Green (Ready) on the waiter's tablet.

### Phase 3: Global Batch View Sync
1.  **Bulk Readiness:** For high-volume items, a cook uses the Batch View to mark "8x Burgers" as ready simultaneously.

2.  **Mass Notification:** The system logic identifies the 8 oldest "Burger" items across all active tickets. Relevant waiters receive simultaneous "Ready for Pickup" alerts, and all corresponding tables update to Green status instantly.

### Phase 4: Unified BUMP & Table Clearance
1.  **Final Dish:** The cook taps the last item on a ticket, which finally activates the unified **BUMP** button at the ticket header (inverting it to solid black).

2.  **The Handshake:** Tapping BUMP moves the ticket to the COMPLETED archive. The Waiter receives a high-priority "ORDER COMPLETE" notification, and the floor plan updates to a "Service Ready" checkmark.

3.  **Cycle Time Logging:** The backend logs the Total Cycle Time (Injection to BUMP) for Admin analytics.

## PART 4: THE ADMIN WORKFLOW
*The command center for oversight, configuration, and emergency system reversal.*

### Phase 1: The Command Center & Live Mini-Map
1.  **Unified Pulse Dashboard:** The Admin logs in to real-time KPIs: Revenue Today, Average Prep Time (from Kitchen Phase 4 data), and Staff Load.

2.  **The Mini-Map:** A high-density, vector-scaled version of the floor plan for passive monitoring.

    - **Visuals:** Free tables are faded; occupied tables are bright. Active requests pulse.

    - **Overlays:** A "Time-at-Table Ring" tracks seating duration against averages. A hovering currency badge shows the live running bill.

3.  **Quick Stats:** Tapping a table reveals the assigned waiter, time of last served dish, and void counts. Red map zones indicate bottlenecks (e.g., excessive wait times or overloaded kitchen queues).

### Phase 2: Observational Oversight & "Void" Execution
1.  **The Waiter Mirror:** The Admin can drill down to see exactly what the waiter sees, but with elevated "Admin Action" capabilities.

2.  **Void Initiation:** To correct errors, the Admin swipes an item and taps the Red Trash/Void Icon.

3.  **System-Wide Reversal (Atomic Transaction):** \* The Admin inputs a Reason Code (Mispick, Quality, Out of Stock) and a "Waste" boolean (for inventory).

    - **Kitchen Sync:** The KDS item turns Bright Red with a "VOID" stamp and an audio cancellation chime sounds.

    - **Waiter/Client Sync:** The item strikes through and moves to a "Voided Items" section. The financial total is automatically corrected.

### Phase 3: Spatial Editor (The Floor Plan Lab)
1.  **Mode Toggle:** The Admin switches to a distinct "Edit Mode" blueprint grid.

2.  **Drag-and-Drop Canvas:** Admin places tables, assigns IDs (e.g., T-15), sets capacities, and groups them into Sectors.

3.  **Live Deployment:** Tapping **"Publish Layout"** instantly pushes the new spatial map to all active Waiter tablets via WebSockets, with zero downtime.

### Phase 4: Staff & Menu Resource Control
1.  **Permissions:** Admin manages staff, assigning strict roles (Cook, Waiter, Manager) that intrinsically limit UI and data access.

2.  **The Digital Pantry (Menu Control):** The central source of truth for items and pricing.

3.  **Emergency Stock Toggles:** If an ingredient runs out, a single tap marks it "Sold Out," instantly graying it out on Waiter tablets and the Client app to prevent dead-end orders.

### Phase 5: Retrospective Analytics
1.  **Performance Heatmaps:** Visual overlays on the floor plan showing high-revenue or fast-turnover tables.

2.  **Void Audit Trail:** A ledger of all Voids sortable by Reason Code to identify training gaps or kitchen station failures.

3.  **Shift Reporting:** Comprehensive exports comparing order injection times to BUMP times, fueling the Average Prep Time KPI.

# TableMate: Feature Acceptance Criteria by Developer Role
This document defines the strict Acceptance Criteria (AC) for the core platform features. A feature is only considered "Done" when all associated criteria are demonstrably met and pass QA validation.

## DEVELOPER 1: The Systems Architect (Backend & Infrastructure)
*Focus: Database integrity, security, and real-time state delivery.*

### Feature 0: Canonical Data Models & Database Migrations
- **AC 1:** Database migrations successfully create tables for Restaurant, Table, Session, Order, OrderItem, Ticket, and Staff with all required relationships (Foreign Keys) and constraints.

- **AC 2:** Status fields (e.g., Table statuses, OrderItem lifecycles) are strictly enforced at the database level using ENUMs.

- **AC 3:** Shared TypeScript types/interfaces mapping exactly to these DB models are generated and published/accessible to the frontend codebase.

### Feature 1: Auth & RBAC (Role-Based Access Control)
- **AC 1:** Successful login generates a JWT that explicitly encodes the user's role (Cook, Waiter, Manager, Owner).

- **AC 2:** Every protected REST endpoint and WebSocket connection rejects requests with a 403 Forbidden if the token's role lacks the required permissions matrix.

- **AC 3:** If an Admin changes a user's role, the user's active token is immediately invalidated, forcing a re-authentication.

### Feature 2: WebSocket Infrastructure & Event Catalog
- **AC 1:** The WebSocket server accepts connections only with valid JWTs and maps the connection to a persistent user presence state.

- **AC 2:** Event broadcasting is strictly role-scoped (e.g., a Cook token never receives FloorPlanUpdated events).

- **AC 3:** Reconnection logic guarantees at-least-once delivery: if a client reconnects after a drop, the backend replays all events missed during the disconnection window.

### Feature 3: Session & Table State Machine
- **AC 1:** An endpoint exists to transition a Table from Free to Occupied. Calling this endpoint automatically generates a new Session record linked to the Table.

- **AC 2:** An endpoint exists to "Close Table". Calling this endpoint clears the live Table state (setting it to Free), records the final total, and saves an immutable Session snapshot.

- **AC 3:** Any state transition automatically triggers the corresponding WebSocket event broadcast to all relevant Waiter and Admin clients.

## DEVELOPER 2: The UI/UX Specialist (Frontend Render Engine)
*Focus: High-performance rendering, state mapping, and human-input ergonomics.*

### Feature 5: The Modifier Modal & Order Item Entry
- **AC 1:** Tapping a menu item opens the Modifier Modal with zero perceptible lag (\< 100ms).

- **AC 2:** Upon modal opening, input focus defaults instantly to the "Comment" text field.

- **AC 3:** The "Submit/Confirm" button is strictly disabled until the user explicitly selects a valid "Guest Slot."

- **AC 4:** The Waiter UI maps OrderItem lifecycle statuses strictly to the design system's semantic tokens (Gray/Pending, Yellow/InProgress, Green/Ready).

### Feature 6: Kitchen Kanban & Queue Management
- **AC 1:** The "Incoming" column renders tickets strictly in order of injection timestamp, completely ignoring Table ID or Order size.

- **AC 2:** The "Batch View" successfully aggregates identical active OrderItems (e.g., "8x Burgers") across multiple distinct tickets.

- **AC 3:** The "BUMP" button on a ticket header remains strictly disabled until every single item within that ticket has been tapped and moved to the "Completed" (Green) state.

### Feature 9: Live Floor Plan Engine
- **AC 1:** Performance Budget: The floor plan component processes incoming WebSocket state patches and fully repaints the layout within 100ms on a mid-range tablet.

- **AC 2:** Table colors and statuses are driven 100% by the WebSocket payload. The client runs zero local inference (e.g., it does not guess a table is occupied just because an order exists locally).

- **AC 3:** Re-rendering a table's state does not trigger any extraneous REST network requests.

### Feature 12: Connection Resiliency & Destructive Actions
- **AC 1:** If the WebSocket connection drops, a full-screen or persistent high-visibility banner immediately mounts to warn the user.

- **AC 2:** While disconnected, all data-writing actions (Submit Order, Bump Ticket, Close Table) are hard-disabled.

- **AC 3:** Tapping "Close Table" triggers a mandatory confirmation modal that explicitly displays the final bill total and item count before allowing execution.

## DEVELOPER 3: The Integrator (Fullstack Business Logic)
*Focus: End-to-end flows, third-party APIs, and Admin tooling.*

### Feature 4: Webhook Payment Pipeline
- **AC 1:** The Client frontend successfully mounts the payment provider SDK (Stripe/Apple Pay), captures the payment method securely, and returns a token without passing raw CC data to the TableMate backend.

- **AC 2:** The Backend webhook listener successfully cryptographically validates the incoming success signature from the payment provider.

- **AC 3:** Upon successful validation, the backend atomically executes three actions: sets Order to Paid, creates the Kitchen Ticket, and fires the WS event to the Kitchen and Waiter.

### Feature 7: The Atomic Void Transaction
- **AC 1:** The frontend Void modal strictly requires the selection of a predefined "Reason Code" and an explicit toggle for is_wasted before submission is allowed.

- **AC 2:** The backend executes the void as a single, atomic DB transaction: it updates the item status, decrements the session total, logs the waste/reason, and queues the new receipt.

- **AC 3:** Executing a void successfully fires a priority WS event that turns the specific item card bright red on the Kitchen Kanban and triggers the KDS audio chime.

### Feature 8: Unified Notification Stream
- **AC 1:** The persistent sidebar mounts and distinctly separates WebSocket events into "Client" and "Kitchen" streams.

- **AC 2:** Events are rendered into the list immediately as they arrive over WS (no visual batching or polling delays).

- **AC 3:** Tapping any notification instantly triggers a route transition/overlay open for the exact Table associated with the alert.

### Feature 10: Admin Spatial Editor
- **AC 1:** In "Edit Mode," the Admin can drag and drop geometric tables onto a grid, assign unique text IDs, and set numerical capacities.

- **AC 2:** Tapping "Publish" saves a new, immutable layout JSON version to the database (preserving historical versions).

- **AC 3:** Publishing triggers a LayoutUpdated WS event, causing all connected Waiter tablets to instantly re-render the new floor plan without requiring a browser refresh.

### Feature 11: Immutable Financials & Analytics
- **AC 1:** The "Average Prep Time" KPI is dynamically calculated on request by querying the delta between injection and bump timestamps on Ticket records.

- **AC 2:** The Admin Dashboard correctly mounts and displays real-time aggregated KPIs (Revenue, Prep Time, Staff Load).

- **AC 3:** API Security: No REST endpoints exist that allow external POST, PUT, or DELETE requests against financial/session-total records.
