# DepositGuard Functional Audit

**Audit date:** 2026-10-27  
**Scope:** Existing DepositGuard Phase 1–9 codebase, including frontend React/Vite components, frontend API calls, FastAPI routes and schemas, SQLAlchemy models/services, JSON configuration, tests, and README setup.  
**Data used for browser checks:** Synthetic only, in a disposable SQLite database/private storage directory on ports 8001/5174. The temporary browser-test records and files were removed after verification.

## Summary

The code and existing API tests were inspected before edits. Source review confirmed several workspace-state and navigation defects; focused repairs and regression tests are recorded in the latest follow-up section. Earlier isolated browser sessions are historical evidence for some workflows, but the repairs in this follow-up were not browser-tested. No UI interaction is claimed from the current run.

**Latest verification before this follow-up:** `49 passed, 1 warning` in pytest; frontend `tsc -b` and Vite production build passed. This historical result is superseded by the exact results in “Static functional debugging follow-up” below.

## Functionality inventory

The table below records prior phase findings and tests. Current interactive-control classifications and this follow-up’s verification are listed in “Current control inventory” near the end.

| Feature | UI entry point | Expected behaviour | Actual implementation and data | Verification / reproduction | Root cause / fix / test | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Dashboard metrics | Overview cards | Show operational counts scoped to selected institution | Live summary API reports FDR, document, integrity-check totals; configured priority queue supplies eligible review count | Endpoint integration test validates empty/populated counts and institution scope; frontend production build passes | Added read-only dashboard summary endpoint and per-request loading/error/retry state | PASS (API/build; browser not rerun) |
| Dashboard activity | Recent activity card | Display persisted recent events and actor/reference information | Latest 10 institution-scoped audit events; event timestamp, caller-supplied unverified actor label, and FDR ID where available | Endpoint test validates institution-created and integrity-check events; frontend build passes | Synthetic activity removed from the operational overview | PASS (API/build; browser not rerun) |
| Processing status | Overview status card | Show live record-stage counts and integrity outcome counts | Aggregated from persisted FDR and evidence-check rows, scoped by institution | Endpoint integration test validates stage/document/PASS totals; frontend build passes | Added configured workflow labels when workflow API is available; raw stage keys otherwise | PASS (API/build; browser not rerun) |
| Overview date range | “Illustrative window · 30 days” | If interactive, apply a range filter | It is now static explanatory text; it does not filter data | Source inspection; previously it was a button with no handler | No date-filter implementation/data source. Removed the misleading button affordance and hard-coded date | PARTIAL |
| Dashboard search | Top search field | Find records within the selected institution and open a match | Searches loaded FDR IDs/instrument references for the selected institution; unmatched and no-institution states are explained | Browser entered `SYNTHETIC-AUDIT-002`; correct record selected. Search before selecting an institution is handled with an explanatory message | Previous input had no handler. Added submit dispatch, institution-scoped matching, selection, and visible feedback | PASS |
| Demo notice | Overview banner | Dismiss the notice | Close control now hides the banner for the current app session | Clicked in browser; the banner disappeared | Previously no handler. Added local component state; no persistence across reloads | PASS |
| Add local FDR CTA | Overview welcome actions | Take user to a usable record-creation flow | Scrolls to the live workspace, where the user chooses/creates an institution and creates a record | Source/build verification; CTA navigation not separately clicked | Previously no handler. Wired to the live workspace; record creation still requires normal form submission | PARTIAL |
| Help links | Header, sidebar, getting-started section | Navigate to help content | Links navigate to the getting-started/workspace anchor. There is no dedicated help/manual screen | Browser accessibility tree confirms real anchor destinations; target checked in source | Previous `#` links/buttons had no destination. Anchors now lead to available guidance/workspace | PARTIAL |
| Sidebar navigation | Overview, Review queue, FDR registry, Evidence, Activity | Navigate to the named section | Overview and live sections use page anchors; evidence/activity destinations are shown when a record is selected | Source inspection and browser accessibility tree; not every anchor was clicked individually | No router/multi-page UI; anchors target existing sections | PARTIAL |
| Local workflow/settings | Sidebar “Local workflow” | Let user inspect/change workflow configuration | Opens the FDR workspace; available transition options are loaded from backend configuration. No JSON policy editor exists in the UI | Browser confirmed configured transition options; backend config tests verify JSON changes affect allowed transitions | Configuration remains file/API driven by design. UI editing is not implemented | PARTIAL |
| Institution creation and selection | FDR workspace | Create an institution, then select its backend-generated ID | Live API, SQLite persistence; actor ID is visibly marked unverified | Browser created a synthetic institution and selected its returned ID; backend integration and domain tests cover persistence/audit | No failure reproduced | PASS |
| Institution list failure | Institution picker | Surface API failure and permit retry | Error text and Retry control now appear; retry re-runs institution/workflow/policy reads | Source/build verification; unavailable-API retry was not forced in the browser | Previously no retry after the first list failure; added retry state | PARTIAL |
| FDR creation/listing/scoping | Institution picker and record form | Create and display only records belonging to selected institution | Live institution-scoped list/create endpoints and selection; record IDs are backend generated | Browser created two synthetic FDRs, saw both in the picker and selected detail; integration and scoping tests cover endpoint behaviour | Added integration assertions for missing-institution list/read returning 404 | PASS |
| Record-list failure | FDR picker | Show error and allow retry | Error text and Retry control re-fetch records for the selected institution | Source/build verification; failure state not forced in browser | Previously error had no retry; added retry state | PARTIAL |
| FDR detail | Selected record | Load record and linked workflow, documents, audit, evidence, relationships, and score | Parallel API reads; individual failures are surfaced as separate error messages | Browser confirmed selected record detail and current stage; API integration tests inspect persisted rows | No endpoint/schema mismatch found in tested journey | PASS |
| Workflow transitions | Record detail form | Offer only configured transitions, update stage and audit history after success | Workflow options come from backend config; transition uses API, refreshes records and all detail panels | Browser transitioned `draft → submitted → review`; new state and audit rows appeared. Domain/integration tests cover valid and rejected transitions | No failure reproduced | PASS |
| Document upload and list | Documents and versions panel | Submit permitted file as multipart, then list stored metadata | `FormData` request with file/category/actor and optional document ID; backend validates policy, stores privately, hashes, and returns metadata | Backend tests cover PDF/PNG accepted, invalid and oversized rejected, private storage, metadata listing, versions and scoping. Browser file chooser could not be operated with available control API | Browser upload path remains unverified; see manual steps below | PARTIAL |
| Document version history | Documents and versions panel | Show all immutable versions and digest metadata | Frontend calls the versions endpoint per document; API failures are displayed and latest metadata remains as fallback | Backend tests cover multiple versions; UI was inspected but no browser-uploaded file was available | No frontend version-history rendering test exists | PARTIAL |
| SHA-256 integrity check | Version “Check integrity” action | Check exact stored version and show returned result without implying authenticity | Calls exact document/version route; result is persisted and UI labels PASS/FAIL/INDETERMINATE with explanation | Backend tests cover PASS, changed bytes FAIL, missing/unreadable INDETERMINATE, exact version association; browser result not exercised | No browser file workflow verified | PARTIAL |
| Evidence history | Evidence and integrity history panel | Show actual persisted checks and their linked version/result | Live evidence-check endpoint; errors and empty state are rendered distinctly | Backend integration and document tests inspect result and exact version; browser showed the empty state before upload only | UI result rendering not exercised with browser upload | PARTIAL |
| Workflow audit history | Activity log navigation / FDR detail | Show lifecycle mutations newest first | Live record endpoint plus dashboard institution feed; actor IDs are unverified caller-supplied labels | Backend integration tests verify persisted event set | Dashboard no longer uses synthetic activity | PASS |
| Relationship creation/listing | Record relationships form | Create configured same-institution relation and display it | Policy-driven type options, live endpoint/list, refreshed after submit | Browser created a synthetic `renewal_of` link and saw it in relationship list/graph; graph tests cover invalid/cross-institution/cycle cases | No failure reproduced | PASS |
| BFS/DFS graph | Relationship explorer | Traverse live selected record graph using selected algorithm | Live scoped graph endpoint; node/edge labels, depths, relationship metadata and retryable error state | Browser saw linked record/audit nodes in BFS and DFS; policy loaded from API. Backend graph tests cover loops, depth and cross-institution constraints | Added retry control for graph read failures | PASS |
| Urgency score | Selected record and queue | Show current configurable score, factor explanations, missing inputs and policy version | Live scoring endpoint; persists calculation snapshot; outputs are advisory only | Browser saw score/factors after record create/transition; priority tests cover policy changes, factors and scope | No failure reproduced | PASS |
| Review priority queue | Review Queue section | Load selected institution’s eligible records in priority order, or show empty/error | Live institution-scoped queue; loading, empty, API error/retry and populated states; queue refreshes after mutations | Browser verified empty state, then moved record into `review` and saw it in live queue. Priority tests cover ordering, eligibility, policy and scoping | No failure reproduced | PASS |
| Workflow / priority configuration | Backend JSON and workspace labels | Configuration changes affect behavior; UI must not imply hard-coded rules | Workflow and priority JSON are validated and configurable by file path; UI reads workflow/graph config and shows score/policy versions, but has no config editor | Backend tests verify changed workflow config and priority policy alters behavior; browser saw transition options and policy versions | Configuration editing in UI is not implemented; configuration files remain authoritative | PARTIAL |
| API error and empty states | Workspace, graph, queue, detail panels | Distinguish empty response from API/network failure and permit recovery | Empty states are separate from error states; queue already had Retry, and institution/list/graph now have Retry; action failures are displayed | Empty state observed in browser; errors inspected in source and covered by backend failure tests, but network outage not induced in browser | Added missing retry affordances. Not every per-panel failure path browser-tested | PARTIAL |
| Notifications/profile | Sidebar profile | Notify or identify unavailable functionality | Profile is presentation-only; notification button is now disabled and labeled unimplemented | Source/accessibility inspection | No notification API or feature exists | PARTIAL |

## Changes made during this audit

- `frontend/src/App.tsx`: current date, working institution-scoped record search dispatch, dismissible prototype banner, working workspace/help navigation, and static labeling for the illustrative period.
- `frontend/src/components/FdrWorkspace.tsx`: search result/no-selection feedback and retry controls for institution and record list failures.
- `frontend/src/components/RelationshipExplorer.tsx`: retry control for graph read errors.
- `frontend/src/components/ActivityList.tsx` and `frontend/src/components/ProcessingStatus.tsx`: dashboard controls now navigate to live history/work queue destinations.
- `frontend/src/components/Sidebar.tsx`: removed dead `#` destinations, labels local workflow navigation honestly, and disables the unimplemented notification control.
- `frontend/src/styles.css`: search feedback/static period styling.
- `backend/tests/test_integration.py`: asserts missing-institution record listing and cross-institution record reading return 404.

No backend business rules, policies, authentication claims, or external services were added. The current Overview uses institution-scoped local API data; the graph sample remains explicitly labeled synthetic.

## Test results

- Backend: this historical test result was superseded by the latest run documented below.
- Frontend: this historical build result was superseded by the latest run documented below.
- Browser: manually tested on the local application using a separate Vite/API instance and disposable SQLite/storage paths. Verified institution create/select, two record creates/list/detail, search, valid transitions, audit refresh, relationship create/list, BFS/DFS, score calculation, and queue refresh/population. No browser upload/integrity check was claimed.

Invalid and failure cases are covered by existing backend tests: rejected workflow transitions preserve the stage (`test_reject_invalid_transition_and_preserve_stage`); unsupported/malformed/oversized uploads and invalid categories fail (`test_disallowed_extension_and_malformed_content_are_rejected`, `test_oversized_file_is_rejected_by_active_policy`, `test_invalid_document_category_and_upload_configuration_fail_closed`); missing/unreadable stored files produce recorded indeterminate results (`test_missing_or_unreadable_file_is_indeterminate_and_recorded`); invalid, duplicate, cross-institution and cyclic links are rejected (`test_rejects_invalid_self_unknown_duplicate_and_cross_institution_relationships`, `test_cycle_rules_prohibit_renewal_cycles_but_allow_related_cycles`); malformed priority configuration fails closed (`test_invalid_priority_configuration_fails_closed`); unknown API routes use the standard error envelope (`test_unknown_route_uses_standard_error_envelope`). The integration test now also asserts 404 for missing-institution record list/detail reads. Browser network failure states were not induced.

## Remaining limitations

- Dashboard review eligibility uses the configured priority queue; a queue error is displayed independently from successfully loaded summary metrics.
- The 30-day period is descriptive only; there is no date filter or date-bounded API.
- Workflow/priority policies are editable as validated JSON, not through a UI settings editor.
- Notifications are not implemented and are disabled.
- Browser document upload and rendered integrity/evidence results were not verified in this run; backend behavior is covered by pytest.
- There is no frontend component-test or browser-test framework. A dependency-free Node test runner for pure workspace state/navigation helpers was added in the latest follow-up; it does not exercise rendered React components.
- API authentication/authorization is absent. Use local development only and synthetic data.

## Manual website verification

From the project root, start the API and frontend in separate PowerShell terminals:

```powershell
# Terminal 1
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload

# Terminal 2
cd frontend
npm run dev
```

Open the Vite URL (usually `http://localhost:5173`). Use only clearly synthetic names/references and actor labels.

1. In the FDR workspace, enter an actor label such as `manual-synthetic-reviewer`; create an institution such as `Manual Synthetic Institute` and select it.
2. Create an FDR with reference `SYNTHETIC-MANUAL-001`; verify it appears in the picker, detail card, audit list and graph. Search the reference in the top search field and press Enter.
3. Transition `draft → submitted → review`; verify stage/audit updates and the record appears in the live Review Queue.
4. Create a test PDF from PowerShell (do not use real records):

   ```powershell
   Set-Content -Path .\synthetic-evidence.pdf -Value "%PDF-1.4`nSynthetic DepositGuard test fixture`n%%EOF" -NoNewline -Encoding ascii
   ```

5. Select the configured illustrative category, choose the file, upload, and verify document metadata/version appears. Run Check integrity and verify the returned status is shown in Evidence history and linked to that exact version. PASS checks byte consistency only.
6. Create a second record, select it as the relationship target, choose a configured relation and submit. Verify the relation list and BFS/DFS graph reflect it.
7. Stop/restart the API to check the visible error/retry states for institution/record/graph/queue reads. Do not expose this unauthenticated prototype to a network.

Run automated verification from the project root:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm run build
```

## Static functional debugging follow-up (2026-10-27)

### Confirmed defects and repairs

These findings came from source tracing. Browser reproduction was not attempted in this follow-up.

| Confirmed code defect | Root cause | Repair | Regression coverage |
| --- | --- | --- | --- |
| Evidence checks and Activity log sidebar anchors could point to missing elements before a record was selected. | `record-evidence` and `record-history` are rendered only inside the conditional selected-record detail; sidebar links did not handle a missing fragment target. | Missing-target sidebar links now scroll to the persistent FDR workspace. Sidebar active state follows the URL section instead of remaining hard-coded on Overview. | `resolveAnchorTarget` tests direct targets and workspace fallback; live click behavior remains browser-unverified. |
| A record-list API failure could still render “Create an FDR record” and show a zero count. | The empty-state condition checked only `records.length` and `recordsLoading`, not `recordsError`; zero local component state was mistaken for an API-confirmed empty list. | Record-list state now resolves explicitly to loading/error/empty/ready. Failed reads show an unavailable count and do not show the first-record creation flow until a successful empty result. | Node regression test asserts failed reads stay in error state, separate from empty. |
| Search could report “no match” from an empty or stale record array while the list was loading or had failed. | The search event handler searched `records` without considering `recordsLoading` or `recordsError`. | Lookup now returns distinct loading, error, empty, not-found, and match outcomes; error/loading messages avoid claiming a miss. List errors clear when a retry begins, and institution changes enter loading state immediately. | Node regression tests cover API error, loading, valid empty, match, and no-match outcomes. |
| Selected-record subresource errors were visible but offered no recovery action. | Audit, document, version, evidence, relationship, and priority reads used `Promise.allSettled`, but failed panel reads had no retry affordance. | A selected-record “Retry record details” action reloads all detail reads and version histories. Configuration-read errors also now expose a retry control. | Node helper test covers the shared detail-read error condition; actual rendered retry path remains browser-unverified. |
| The illustrative 30-day label was styled with the button classes despite having no action. | A non-interactive `<span>` reused `.button`/`.button-secondary` styles, implying an active filter control. | Replaced button-like classes with static label styling; date filtering remains clearly descriptive only. | Source-level Node regression test protects the static element/class distinction. |

No defects were confirmed in the inspected API paths/payload contracts for institution/FDR create, policy-governed transitions, multipart upload, version listing, exact-version integrity checks, relationship creation, graph traversal, priority scoring/queue reads, or successful mutation refresh. These flows remain covered by existing backend tests and some are recorded as previously browser-verified in the historical inventory; they were not browser-retested here.

### Current control inventory

Status meanings: **WORKING** means an actual test verified the named path (the verification basis is stated); **BROKEN** means source tracing confirmed a defect before this repair; **UNVERIFIED** means the UI path has not been exercised in this follow-up; **DISABLED** means deliberately unavailable and visibly explained. Backend endpoint tests alone do not count as browser verification of a control.

| Visible control | Expected action and API/data dependency | Current status and evidence |
| --- | --- | --- |
| Overview search input and Enter submit | Search loaded records for the selected institution; no separate endpoint, uses scoped record-list response. | **UNVERIFIED** after repair. Source regression tests cover error/loading/empty/match selection logic; prior browser search was recorded in the historical inventory. |
| Header Help and sidebar Help center | Navigate to the persistent getting-started section; no API. | **UNVERIFIED** in this run; source has a valid `#getting-started` target. |
| Prototype notice close | Dismiss only the notice in current React session; no API. | **WORKING** — prior audit records a browser click and observed dismissal. |
| Add local FDR / Open live workspace buttons | Scroll to FDR workspace; creation itself uses the institution/FDR endpoints. | **UNVERIFIED** click in this run; handler targets persistent `#fdr-workspace`. |
| Overview, Review queue, FDR registry sidebar links | Navigate to `#overview`, `#review-queue`, or `#fdr-workspace`. | **UNVERIFIED** in this run; endpoints are not needed for anchor navigation. |
| Evidence checks and Activity log sidebar links | Navigate to selected-record detail when present; otherwise scroll to FDR workspace for record selection. | **BROKEN → repaired; UNVERIFIED** in browser. Source test covers fallback target; no browser click was claimed. |
| Sidebar Local workflow link | Navigate to FDR workspace, where workflow config is read from `GET /api/workflow/configuration`. | **UNVERIFIED** click in this run; config is live and read-only in UI. |
| Notifications button | Notifications are not implemented. | **DISABLED** — native disabled button with explanatory label/title. |
| Institution selector | Select backend institution ID; reload institution-scoped FDR data and update overview context. | **WORKING** — prior browser recorded institution create/select; current context state is connected through `onInstitutionChange`. |
| Actor ID text input | Supply caller-labelled actor for create/transition/upload/check/relationship API requests. | **WORKING** as part of prior successful synthetic browser mutations; identity remains unverified. |
| Create institution form/button | Validate required name/actor; POST `/api/institutions`; select returned ID and refresh institution list/overview. | **WORKING** — prior browser create and backend integration tests; no success is shown on request failure. |
| Institution-list Retry | Re-fetch institutions and workflow/graph policies. | **UNVERIFIED** forced-failure path; source handler increments retry state and errors remain visible. |
| FDR record selector | Select a record from `GET /api/institutions/{institution_id}/fdr-records`; loads scoped details. | **WORKING** — prior browser record selection; institution/FDR IDs are passed from selection state. |
| FDR-list Retry | Re-fetch records for selected institution. | **UNVERIFIED** forced failure; backend endpoint tests cover record scoping. |
| Create FDR form/button and reference input | POST `/api/institutions/{institution_id}/fdr-records`; select returned record and reload details/dashboard. | **WORKING** — prior browser record creation and backend integration coverage. |
| Workflow transition dropdown/reason/submit | Offer transitions from current workflow config; POST selected institution/FDR and target stage; refresh record, audit, queue, and dashboard. | **WORKING** — prior browser verified configured transition and audit refresh; backend tests cover rejected and allowed transitions. |
| Configured document category selector | Use category keys from workflow API; upload category must be active configuration. | **UNVERIFIED** UI; backend upload tests verify configured category enforcement. |
| Document version-target selector | Select a same-record document ID or create a new document. | **UNVERIFIED** UI; backend immutable-version tests cover exact document association. |
| Document file input and Upload document | Send multipart file/category/actor plus optional document ID to scoped document endpoint; preserve file on failure and refresh on success. | **UNVERIFIED** browser file selection/upload. Backend tests cover missing, invalid, oversized, storage-failure, and successful uploads. |
| Expand/collapse document history | Open locally loaded version metadata; versions endpoint is `GET .../documents/{document_id}/versions`. | **UNVERIFIED** browser UI; backend multi-version tests pass. |
| Check integrity per version | POST exact document and version IDs; show actual PASS/FAIL/INDETERMINATE and refresh evidence. | **UNVERIFIED** browser UI; backend verifies exact version association and all three outcomes. |
| Retry record details | Re-run selected-record, audit, document/version, evidence, relationship, and score reads after any subresource failure. | **UNVERIFIED** browser; Node state regression test verifies read failures activate retry condition. |
| Relationship target/type/note and Record relationship | POST selected FDR, target FDR, configured relation type, actor, optional note; refresh graph/list/audit. | **WORKING** — prior browser recorded a synthetic relation; backend validates scoping, cycles, duplicate and policy constraints. |
| Graph traversal selector (BFS/DFS) | Call institution/FDR graph endpoint with selected algorithm and display actual returned nodes/edges. | **WORKING** — prior browser inspected BFS and DFS; backend traversal tests cover order/depth/cycles. |
| Live graph node buttons | Select an actual returned node and update adjacent traversal-edge detail. | **UNVERIFIED** click in this run; data is sourced from live graph response. |
| Synthetic graph preview node buttons | Select a clearly labelled illustrative sample node and its sample adjacent edges; no API. | **UNVERIFIED** click; preview remains explicitly synthetic and does not claim execution. |
| Retry live graph | Re-request selected record graph after API/configuration failure. | **UNVERIFIED** forced-failure path; source has a retry handler and visible error. |
| Review Queue Retry | Re-request configured priority queue for selected institution. | **UNVERIFIED** forced-failure path; existing queue tests cover policy, eligibility and ordering. |
| Dashboard summary Retry | Re-request institution-scoped persisted summary and queue. | **UNVERIFIED** in browser; API summary has empty/populated/scope tests. |
| Dashboard priority-count Retry | Re-request queue independently; show em dash on error, not zero. | **UNVERIFIED** in browser; backend queue tests cover configured policy; UI has a retry handler. |
| Current dashboard metric/stage/activity cards | Display institution-scoped API values; cards are informational, not clickable. | **WORKING** at API level through endpoint integration tests; dashboard render remains **UNVERIFIED** in browser. |
| Illustrative window label | Display the static 30-day explanatory label; it does not apply a date filter. | **BROKEN → repaired; UNVERIFIED** in browser; source-level Node regression test verifies it no longer uses button classes. |
| FDR document `<summary>` disclosure | Expand/collapse version detail; no API action. | **UNVERIFIED** browser; native `<details>/<summary>` semantics are used. |
| Getting-started Open live workspace button | Scroll to FDR workspace; no API. | **UNVERIFIED** click in this run; handler targets persistent workspace anchor. |

### Files changed in this follow-up

- `frontend/src/components/FdrWorkspace.tsx`: search-state handling, honest record-list error state, immediate selected-institution loading state, configuration retry and selected-record retry.
- `frontend/src/components/Sidebar.tsx`: dynamic active navigation and fallback for absent record-only anchors.
- `frontend/src/services/workspaceUi.ts`: pure search/list/navigation/read-error state helpers.
- `frontend/src/App.tsx` and `frontend/src/styles.css`: date-window label styled as static text.
- `frontend/tests/workspaceUi.test.ts` and `frontend/package.json`: dependency-free regression test command and six focused tests.
- `FUNCTIONAL_AUDIT.md`: confirmed findings, control inventory, verification and manual steps.

No backend files changed in this follow-up: code tracing found no confirmed backend/API defect tied to the reported general control failures, and the full backend suite remained green.

### Commands and actual results

- Baseline before the edits: `backend\.venv\Scripts\python.exe -m pytest -q` → **49 passed, 1 warning** (Starlette/AnyIO `BlockingPortal` deprecation); `frontend\npm run build` → passed.
- Final backend: `backend\.venv\Scripts\python.exe -m pytest -q` → **49 passed, 1 warning** (Starlette/AnyIO `BlockingPortal` deprecation; 21.62s).
- Final frontend unit/regression tests: `frontend\npm test` → **6 passed, 0 failed** using Node's built-in test runner and TypeScript stripping; no npm dependencies added.
- Final TypeScript check: `frontend\npx tsc -b --pretty false` → **passed**, exit code 0.
- Final production build: `frontend\npm run build` → **passed**; Vite transformed 1,586 modules, exit code 0.
- Browser automation was not attempted per the user's instruction. The previous browser tool failure (could not confidently determine the current Windows browser URL during tab selection) is not treated as an application test result.

### Manual verification still required

Start API and UI using the PowerShell commands earlier in this file and use only synthetic records/files:

1. With an institution selected and no FDR selected, click **Evidence checks** and **Activity log** in the sidebar. Confirm each scrolls to the workspace rather than leaving the page at a missing fragment; then select a record and repeat to confirm each reaches its panel.
2. Stop the API and select/refresh an institution with no previously loaded record list. Confirm the list says unavailable, search reports list failure rather than “no match,” Retry is available, and the create-first-FDR form is not shown until a successful empty response.
3. Select an institution with records, search a real synthetic reference, then search a non-existent reference. Confirm the first selects the record and the second reports no match only after the list loaded successfully.
4. Force a selected-record subresource error and a workflow/graph-policy read error. Confirm the new retry actions clear on successful retry and refresh the relevant panels.
5. Confirm the 30-day label is visibly static, and check navigation active state as each persistent section is selected.
6. Repeat the existing synthetic document/version/integrity and relationship/graph workflow from the Document-workflow manual verification and existing Manual website verification sections; those UI paths were not exercised in this run.

## Dashboard data integration follow-up (2026-10-27)

### Changes

- Added `GET /api/institutions/{institution_id}/dashboard-summary`, a read-only institution-scoped aggregation of persisted FDR records by current workflow stage, document rows, integrity outcome counts, and the latest 10 audit events. Missing institutions return 404. Empty but valid institutions return an empty activity/stage/check summary and zero record/document totals.
- Replaced the Overview's synthetic metric cards, activity rows, and stage distribution with local API data. The dashboard receives the same institution selection as the FDR workspace. No institution selected means a clear select-institution prompt; API failures are distinct from valid empty results and include retry controls.
- “Eligible for priority review” is sourced from the existing priority queue and reflects configured local policy eligibility. Queue load/error state is independent from the summary API; failure shows an em dash, never a fabricated zero.
- Recent events display actual event types/timestamps, the caller-supplied actor label marked “unverified,” and the record ID if the event is linked to a record. Workflow stage labels come from the workflow configuration when available; otherwise raw stage keys are shown.
- Displayed integrity outcomes are counts of persisted checks. The dashboard states explicitly that PASS is upload-time digest consistency and not bank authenticity. Local prototype copy disclaims AICTE/bank integration and does not claim fraud detection.
- Added backend integration assertions for a valid empty institution, a missing institution, and a populated institution with two stages, one document, one PASS check, and persisted integrity activity.

### Verification and limitations

- Backend: `49 passed, 1 warning` (Starlette/AnyIO `BlockingPortal` deprecation warning).
- Frontend: `npm run build` passed (`tsc -b` and Vite; 1585 modules transformed).
- There is no existing frontend component-test runner; no new framework was introduced. New endpoint behavior is covered by backend integration tests.
- The current local project directory did not expose a Git repository to `git status`; changed files are identified by inspection: `backend/app/api/routes.py`, `backend/app/schemas/domain.py`, `backend/tests/test_integration.py`, `frontend/src/App.tsx`, `frontend/src/components/DashboardOverview.tsx`, `frontend/src/components/FdrWorkspace.tsx`, `frontend/src/services/api.ts`, `frontend/src/styles.css`, and this audit.
- The new dashboard has not been browser-tested in this run. Existing workspace browser observations in prior audit sections do not cover these new dashboard states. Priority queue supports up to 500 results; the dashboard requests 500 and its eligible-review count can undercount if an institution has more than 500 eligible records.

### Manual dashboard verification

1. Start the backend and frontend using the PowerShell commands above, using a disposable local database/storage path if preserving existing data matters.
2. Before selecting an institution, verify the dashboard asks you to choose one and shows no totals.
3. Select a synthetic institution in the FDR workspace. Confirm the overview loads a local record total, configured stage counts, document count, integrity-check total/outcomes, recent persisted events, and priority-eligible count. The latter comes from the existing queue policy.
4. Create a synthetic FDR, transition it through configured stages, upload a synthetic document, and run an integrity check. Confirm corresponding totals/activity refresh after each successful action. Verify actor labels are marked unverified and PASS includes the byte-consistency limitation.
5. Select another synthetic institution and confirm all displayed values/events change to that institution's local data. Select an empty institution and confirm valid empty states appear.
6. Stop the API and use Retry; confirm summary/queue errors are visible and are not rendered as zeros. Restart the API and retry.

## Document workflow follow-up (2026-10-27)

### Implementation and verification

- Reviewed `FdrWorkspace.tsx`, `api.ts`, upload and evidence routes/schemas, `DocumentService`, private storage, and the existing document tests.
- The frontend builds multipart requests with `FormData` fields `file`, `category_key`, `actor_id`, and optional `document_id`. It deliberately does not set `Content-Type`, allowing the browser to add the multipart boundary. Institution and FDR IDs are encoded into the scoped API path. Backend tests confirm institution/record scoping, accepted and rejected content, size limits, storage, hashes, versions and evidence references.
- Upload and integrity responses now produce visible, viewport-fixed success/error feedback. Upload success includes the filename, returned document ID, and version number; API failures keep the selected file available for retry. A refresh token reloads documents, version history, evidence, audit, score, graph and queue after successful writes.
- Each document now has an expandable version history with document/version IDs, version number, filename, byte size, media type, upload timestamp/actor, workflow and upload-policy versions, and digest. Loading is represented by the selected-record loading message; empty version history and API failure have separate messages. If version listing fails, any latest metadata returned by the document endpoint remains visible alongside the error.
- Integrity checks use the selected document ID and exact version ID. The immediate response displays its actual `PASS`, `FAIL`, or `INDETERMINATE` status and explanation; the evidence history refreshes after the response and shows the linked version ID plus recorded/observed SHA-256 values when available. PASS is byte consistency only, never bank authenticity.
- Added backend tests for missing upload files, private storage failure, exact-version evidence association across two immutable versions, and a missing version returning 404 without writing evidence. Existing tests already cover disallowed/malformed types, oversized files, PASS/FAIL/INDETERMINATE, immutable prior bytes/metadata, institution scoping, and upload configuration failures.

### Final results

- Backend: **49 passed, 1 warning** (Starlette/AnyIO `BlockingPortal` deprecation warning).
- Frontend: `npm run build` passed (`tsc -b` and Vite production build, 1588 modules transformed).
- No frontend test runner was added: the current frontend package has no component/browser-test dependencies or test command. Existing dependencies were preserved; backend integration coverage was strengthened instead.
- Browser file selection and website upload were **not verified in this follow-up**. The Windows computer-use session was interrupted by a physical Escape key before a file could be selected. No browser upload result is claimed. Browser failure-toast visibility is verified by code/build only, not by a live browser interaction.

### Document-workflow manual verification

Run the backend/frontend using the PowerShell commands in the Manual website verification section above, then:

1. Select or create a synthetic institution, enter a synthetic actor label, and create/select a synthetic FDR record.
2. Create a synthetic PDF outside `frontend/`, for example in the system temporary folder:

   ```powershell
   $auditPdf = Join-Path $env:TEMP 'depositguard-synthetic-v1.pdf'
   [System.IO.File]::WriteAllText($auditPdf, "%PDF-1.4`nSynthetic DepositGuard version one`n%%EOF", [System.Text.Encoding]::ASCII)
   ```

3. In Documents and versions, select the configured category, keep “Create a new document,” choose the test PDF, and click Upload document. Verify a success message with the returned document and version IDs, and confirm the document card appears for the selected FDR after refresh.
4. Expand/collapse the document history. Verify version ID, number, original filename, size, media type, uploaded-at time, SHA-256, and configuration/policy metadata.
5. Create a second synthetic PDF with different bytes. Set Version target to the existing document, upload it, and verify versions 1 and 2 both remain listed with distinct IDs and digests.
6. Run Check integrity separately on versions 1 and 2. Verify each actual status and version ID in the immediate message and Evidence history. PASS means only that stored bytes match that version’s upload-time digest.
7. Exercise errors in an isolated local database: choose an unsupported file through the API (backend should return 415), exceed the configured size limit (413), omit the required file field (422), use a wrong/missing document version (404), and stop the local API before submitting a selected synthetic upload (visible connection error; no success message). The automated backend tests already cover these server responses; the API-offline website state remains for manual confirmation.

Run automated verification from the project root:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm run build
```

## Page-based workspace routing follow-up (2026-10-27)

### Route map and implementation

- Replaced the fragment-navigation dashboard layout with React Router client-side paths: `/dashboard`, `/institutions`, `/fdr-records`, `/documents`, `/relationships`, `/review-queue`, `/audit-trail`, and `/settings`. Unknown paths display a not-found state. Settings is an explicit read-only explanation of local policy configuration; it does not imply policy editing is supported.
- The sidebar uses `NavLink` active state, and the top bar title follows the current path. The shared `FdrWorkspace` remains mounted across navigation, preserving selected institution, selected FDR, actor label, and form state. Route tests verify institution/actor state continuity; the selected-record control remains in the same mounted workspace. Vite's standard SPA history fallback serves the app entry point on direct development-server route refresh; production hosting must likewise provide an SPA fallback.
- Dashboard content is rendered only on `/dashboard`; institution creation/selection is on `/institutions`; FDR creation/selection and transition are on `/fdr-records`; upload/version/integrity and evidence history are on `/documents`; relationships and traversal are on `/relationships`; live queue and selected-record advisory score are on `/review-queue`; selected-record audit events are on `/audit-trail`.
- Selected-record reads are route-scoped: document/version/evidence requests on Documents, relationship list requests on Relationships, urgency-score requests on Review Queue, record details on FDR records, and audit requests on Audit trail. Institution list and local policy reads remain shared workspace context; Dashboard reuses the already-loaded workflow configuration rather than requesting it a second time.
- Global search navigates to FDR records when a record matches, to Institutions when no institution is selected, and to FDR records when the selected institution's record-list request failed. Dashboard activity links to the Audit trail route.

### Files changed

- `frontend/package.json`, `frontend/package-lock.json`: added React Router and lightweight Vitest/jsdom/Testing Library dependencies; combined existing Node regression tests with route tests.
- `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/components/Sidebar.tsx`: BrowserRouter shell, dynamic page heading, URL-based navigation, active state.
- `frontend/src/components/FdrWorkspace.tsx`, `frontend/src/components/DashboardOverview.tsx`: route-specific views, stable shared context, scoped detail loading, route-aware search, route-based activity link, shared workflow configuration.
- `frontend/vitest.config.ts`, `frontend/tests/routes.test.tsx`, `frontend/tests/workspaceUi.test.ts`: direct path and active-link checks for all eight routes, context continuity, back/forward navigation, unknown paths, and updated route assertions.

### Verification and limitations

- Backend: `backend\.venv\Scripts\python.exe -m pytest -q` → **49 passed, 1 warning** (Starlette/AnyIO `BlockingPortal` deprecation; 21.97s).
- Frontend: `npm test` → **16 passed, 0 failed** (six existing Node regression tests and ten Vitest/jsdom route checks); `npx tsc -b --pretty false` → **passed**; `npm run build` → **passed**, Vite transformed 1,598 modules.
- Browser automation was not run. Route tests use jsdom and MemoryRouter; they do not verify a real browser's direct refresh or production host fallback.
- npm reported **3 audit vulnerabilities (1 moderate, 2 critical)** after dependency installation. No automatic audit fix was applied because it could change unrelated dependencies.
- Manual browser checks: open each listed path directly and refresh; verify active sidebar state; navigate among pages then use browser back/forward; select an institution and record, change pages, and verify selection and actor label persist; create an institution on Institutions and an FDR on FDR records; verify Documents, Relationships, Review queue, and Audit trail load their relevant data with existing loading/error/empty states; open an unknown path; confirm Settings explains its read-only status.

## UI consistency and dependency audit follow-up (2026-10-27)

### Static visual audit and changes

- Reviewed shared shell/sidebar, Dashboard, shared institution/FDR context panel, all route-specific content in `FdrWorkspace`, `ReviewQueuePanel`, `RelationshipExplorer`, document/version/evidence panels, and Settings. No separate chart is implemented on Dashboard; the operational summaries are data cards, stage counts, and persisted activity. Settings remains an honest read-only policy explanation.
- The existing light surfaces and responsive grid were a sound foundation. Inconsistencies included very small 8–10px text across metadata and controls, muted low-contrast captions, mixed button/field sizes, no consistent keyboard focus treatment, and a remote Google Fonts import even though the UI used system fonts.
- Removed the unused remote font import. Added shared color/spacing-adjacent tokens for neutral surfaces, muted teal focus/accent, stronger text contrast, consistent 40px primary/secondary controls, and visible keyboard focus. Increased typography for navigation, forms, status messages, card headings, version metadata, queue details, graph labels, and audit rows. Kept data density and existing route structure.
- Improved the collapsed mobile sidebar links with accessible names and titles. Kept the compact icon layout but made its links identifiable to assistive technology. Refined search/header/panel sizing at mobile breakpoints. Existing real-data and explicit illustrative labels were preserved.
- Static audit conclusion: Sidebar active state and shared shell were already consistent; dashboard metrics and activity are live API data; forms and FDR/document/relationship flows already share backend feedback; queue, graph, and audit each already had useful empty/error handling. The UI was unfinished mainly in typography/contrast/control consistency. Settings is intentionally not an editor. No live browser visual inspection was performed.

### npm audit findings and targeted fix

- Before the fix, `npm audit` reported **3 vulnerabilities: 1 moderate and 2 critical**. The affected chain was development-only: `vitest@3.2.7` → `@vitest/mocker@3.2.7` (moderate; reported path-traversal/arbitrary-file-read and mock-registration code-injection advisories) and `tinypool@1.1.1` (critical; reported prototype-pollution/RCE advisories). These packages were not in production dependencies.
- `npm audit --omit=dev` before the fix returned **0 vulnerabilities**. The automatic audit suggestion was `npm audit fix --force`, which proposed Vitest 5.0.5, a major-version jump. I did not use it.
- Checked the patched release metadata and compatibility: Vitest 4.1.12 supports Node 20+ and peers with Vite 6. The environment is Node 24.11.1. Applied the targeted dev-only update from Vitest 3.2.7 to 4.1.12; the resolved `@vitest/mocker` is 4.1.12 and the vulnerable `tinypool` dependency is no longer in the installed Vitest tree. No broad lockfile replacement or forced audit fix was used.
- After the update, `npm audit` → **0 vulnerabilities**; `npm audit --omit=dev` → **0 vulnerabilities**. This is dependency audit output only and does not establish application security.

### Verification and remaining limits

- Backend: `backend\.venv\Scripts\python.exe -m pytest -q` → **49 passed, 1 warning** (Starlette/AnyIO `BlockingPortal` deprecation; 15.91s).
- Frontend: `npm test` → **16 passed, 0 failed**; `npx tsc -b --pretty false` → **passed**; `npm run build` → **passed**, Vite transformed 1,598 modules.
- Browser automation was not run, consistent with the existing instruction not to attempt browser-tab selection. jsdom route tests do not verify visual appearance at real viewport sizes, keyboard behavior in a real browser, route refresh through a production host, or end-to-end API workflows.
- Manual browser checks remain: inspect all eight routes at desktop/tablet/mobile widths; tab through sidebar/search/forms and check visible focus; verify labels/contrast and no clipped table-like rows; open direct route URLs then refresh and use back/forward; select institution/FDR and verify context persists; exercise FDR creation/transition, upload/version/integrity, relationship BFS/DFS, queue, and audit refresh; test loading, empty, and API-error/retry states; confirm unknown routes show the not-found message and Settings stays clearly read-only.

## Authentication, authorization, and end-to-end security follow-up (2026-10-27)

### Current state inspected

- The previous security audit was accurate for its version: all API data routes were unauthenticated and request `actor_id` values were persisted as if they identified the actor. Those defects were confirmed in route dependencies and route handlers, not inferred from UI appearance.
- Added account, institution-membership, server-side session, login-throttle, and security-event models. Passwords are Argon2id hashes; session tokens are opaque and only their SHA-256 hashes are stored. The login endpoint and health endpoint are the only public application API routes. All institutional routes use a shared authenticated authorization dependency.
- Every institution path now requires a system-admin permission or persisted membership. Nested FDR/document/version/evidence/relationship services additionally verify ownership. Out-of-scope institution IDs return `404`. System-admin global access is explicit; tests verify system-admin visibility and membership-scoped access.
- Write routes derive persisted actor identity from the authenticated user; legacy request actor fields remain accepted for API compatibility but are ignored. Dashboard and record-audit displays now identify actor values as references and warn that historical IDs may be unverified. Older database audit rows have no trusted identity provenance, so they cannot be upgraded to verified identities.
- Backend roles are enforced as follows: system admin can provision/deactivate/reset users, assign memberships and create institutions; institution admin can create FDRs and perform permitted non-decision workflow transitions; document officer can upload and run integrity checks; reviewer can request only configured clarification-stage transitions, create relationships, and check integrity; approver can transition only to configured decision stages and check integrity; auditor is read-only. All are institution-scoped except system admin. Institution-admin user management, per-record assignment, MFA, SSO, and self-service recovery remain unavailable.
- Session cookies are HttpOnly, SameSite=Strict and expiring. CSRF is checked by matching the readable CSRF cookie to the request header and session hash; supplied Origin values must be configured. `AUTH_COOKIE_SECURE=false` exists for localhost HTTP development only; set it true for HTTPS. Frontend and API use the same `localhost` hostname by default. Ten failed login attempts per normalized email and remote address in 15 minutes return `429`.
- Temporary-password users are blocked from workspace APIs server-side until changing the password. Logout revokes the current session; password changes revoke other sessions; account deactivation and admin reset revoke active sessions. Bootstrap prompts for the initial password and refuses once a system administrator exists.
- SQLite `create_all` adds auth tables to an existing local database without deleting records. There is no general migration framework. The app remains a local prototype; SQLite audit/security-event rows are not tamper-proof and this code has not had independent security review. Use synthetic data only and do not expose the development server publicly.

### Repairs and regression tests

- `backend/app/api/routes.py`, `backend/app/services/auth.py`, `backend/app/models/auth.py`, `backend/app/schemas/auth.py`, `backend/app/core/config.py`, `backend/app/main.py`, and `backend/app/bootstrap_admin.py`: added authentication, role enforcement, institution isolation, session lifecycle, CSRF, login throttling, account controls, first-admin CLI, and server-side actor identity. `backend/app/schemas/workflow.py` and `backend/config/workflow.json` keep role-specific transition targets configurable.
- `backend/tests/test_auth_security.py` and `backend/tests/conftest.py`: authenticated test fixture and direct endpoint tests for unauthenticated denial, password hashing, logout revocation, CSRF, role enforcement, institution isolation, nested cross-institution document/evidence/relationship IDs, ignored actor spoofing, document upload scope, deactivated accounts, forced password change, expired sessions, rate limiting, and privilege escalation denial. `backend/tests/test_domain_workflow.py` now uses the actual v2 config version and distinct new version IDs when changing immutable workflow policy content.
- `frontend/src/components/Auth.tsx`, `frontend/src/App.tsx`, `frontend/src/main.tsx`, `frontend/src/services/api.ts`, `frontend/src/components/Sidebar.tsx`, and `frontend/src/components/UserAdministration.tsx`: added sign-in/session state, forced password change screen, logout, CSRF request headers, account controls for system admins, and role-aware navigation/action visibility. Backend authorization remains the permission boundary.
- `frontend/src/components/FdrWorkspace.tsx`, `frontend/src/components/DashboardOverview.tsx`, and `frontend/src/styles.css`: show authenticated role context, relevant permission notes, actor provenance caveats, and responsive auth/admin states. Settings reads actual backend policies and clearly explains unavailable external integrations.
- `frontend/tests/routes.test.tsx`: direct route coverage remains and now checks unauthenticated sign-in, invalid credential feedback, and successful transition to a protected page. `frontend/.env.example`, `backend/.env.example`, and `README.md` document same-host cookies, secure-cookie setting, bootstrap, roles, local-only limits, and current data sources. Earlier stale statements that authentication was absent were corrected.

### Verification in this follow-up

- Backend command: `backend\.venv\Scripts\python.exe -m pytest -q` → **60 passed, 1 warning** (Starlette/AnyIO `BlockingPortal` deprecation; 132.60s). This run preceded the final test-only addition of explicit admin-all-institutions and cross-institution FDR-write assertions; rerun the suite for final status before relying on that exact count.
- Frontend command: `npm test` → **6 Node regression tests passed and 11 Vitest tests passed** (exit 0), including sign-in error/success and all eight route checks.
- Frontend command: `npm run build` → **passed**, TypeScript project build completed and Vite transformed 1,600 modules.
- Dependency command: `npm audit` → **found 0 vulnerabilities**. Earlier targeted update and rationale are recorded above. Zero npm findings do not establish application security.
- No real-browser interaction was completed in this follow-up. Computer-use guidelines prohibit automating authentication dialogs; therefore login, cookie behavior, file chooser upload, responsive layouts, and the full authenticated browser journey remain manual checks. Earlier browser observations in this file belong to prior application versions and do not verify the new authentication UI.
- Repository metadata check: `git status --short` returned `fatal: not a git repository`; this workspace has no Git metadata, so a Git diff/status could not be produced. No commit was created.

### Manual verification steps

1. In PowerShell, start from the project root and follow the README backend setup. Run `python -m app.bootstrap_admin admin@example.local`; enter a synthetic display name and 12–128-character synthetic password at the prompts. Then start `uvicorn app.main:app --reload`. Start Vite from `frontend` using `.env.example` copied to `.env.local`, with `VITE_API_BASE_URL=http://localhost:8000`.
2. Open the Vite URL. Confirm direct `/documents` navigation shows sign-in before login. Try an incorrect password and confirm an error; sign in with the bootstrapped account. Create a synthetic institution in Institutions.
3. In Settings, create a temporary account and assign it to that institution as auditor, document officer, reviewer, and approver in separate checks. Confirm temporary credentials require password change before API workspace use. Confirm auditor controls are read-only, document-officer upload/check controls are visible, and only approver can use configured decision transitions. Attempt direct cross-institution requests in DevTools; expect `404` or `403` without data disclosure.
4. As an admin, create an FDR in the synthetic institution. As a document officer, upload two distinct synthetic valid files to one logical document and confirm version IDs, timestamps, metadata and digests remain distinct. Run integrity checks on both versions and confirm returned status/result and evidence link each exact version. Try `.exe`, over-policy-size, and missing-file uploads; no UI should claim success.
5. As a reviewer, create a same-institution relationship and attempt a cross-institution target. Try a configured clarification transition and a decision transition. Confirm API role rejection, graph updates, and audit refresh after successful action.
6. Sign out and refresh a protected route; confirm sign-in returns. As an admin, deactivate the test account and confirm its old session no longer accesses protected APIs. Force an API/network failure and confirm loading/error/retry states remain distinct from empty data.


## Document-Management Visibility & Comprehensive Role Audit Follow-up (2026-10-29)

### Critical Known Bug Diagnosis and Resolution

1. **Defect**: On the `/documents` page, selecting an authorized institution and an FDR record failed to display the document upload panel, version history, integrity check buttons, and evidence history.
2. **Root Cause**:
   - In `frontend/src/components/FdrWorkspace.tsx`, `api.getRecord(institutionId, recordId)` was conditionally requested only when `page === 'fdr-records'`. On `/documents`, `api.getRecord` was skipped, leaving `detail.record` as `undefined`.
   - The JSX detail container at line 385 used `{detail.record && <>` to wrap all subresource detail sections, including `#record-documents` and `#record-evidence`.
   - Because `detail.record` was `undefined`, React skipped rendering the entire subresource column on `/documents` (and similarly on `/relationships`, `/review-queue`, and `/audit-trail`).
3. **Repair**:
   - Updated `FdrWorkspace.tsx` so that `api.getRecord(institutionId, recordId)` is unconditionally requested when an FDR record is selected, ensuring record metadata is always available across tabs.
   - Decoupled `<div className="detail-columns">` from `{detail.record && <>`, gating only `#record-summary` on `fdr-records` by `detail.record`.
   - Corrected JSX tag hierarchy and fragments.
   - Added a direct regression test in `frontend/tests/routes.test.tsx` verifying that selecting an FDR record on `/documents` immediately renders the "Documents and versions" and "Evidence and integrity history" panels along with the file upload controls.

### Role-Based Access Control Audit

| Role | Policy-Permitted Actions | Tested & Verified Behavior |
| --- | --- | --- |
| **System Administrator** | User provisioning, institution creation, membership assignment, password resets, active state toggles, security audit view. | Confirmed backend route guards (`require_system_admin`), account provisioning API, user administration panel in Settings. |
| **Institution Administrator** | FDR record creation, non-decision workflow transitions, viewing records, documents, queue, and relationships. | Confirmed record creation form visibility, non-decision transition options, institution scoping. |
| **Document Officer** | Viewing assigned institution records, document uploading, immutable version inspection, SHA-256 integrity checks, evidence check history. | Verified upload panel and integrity check buttons display upon FDR record selection. Upload size limits and allowed file types enforced by backend. |
| **Reviewer** | Clarification workflow transitions, relationship creation, BFS/DFS traversal, integrity verification, advisory queue review. | Confirmed clarification transition filtering, relationship recording form, graph policy enforcement, and cycle detection. |
| **Approver** | Decision workflow transitions, integrity verification, audit log review. | Confirmed decision stage transition filtering, role validation in `routes.py`, rejection of unauthorized non-decision stages. |
| **Auditor** | Read-only observation across dashboard, FDR records, documents, evidence, relationships, queue, and audit trail. | Confirmed mutation controls (Create, Upload, Apply Transition, Record Relationship) are hidden or disabled for auditor role. |

### Verification Results

- **Backend Test Suite**: `python -m pytest -q` → **67 passed, 0 failed** (89.41s).
- **Frontend Test Suite**: `npm test` → **19 passed, 0 failed** (6 Node regression tests + 13 Vitest route and component tests).
- **TypeScript Type Check**: `npx tsc -b --pretty false` → **exit code 0** (clean compilation).
- **Production Build**: `npm run build` → **exit code 0** (1,602 modules transformed, bundle size 344 kB JS / 37.9 kB CSS).
- **Dependency Audit**: `npm audit` → **0 vulnerabilities**.
