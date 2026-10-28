# DepositGuard

DepositGuard is a local prototype foundation for exploring evidence-driven FDR verification and lifecycle assurance. It represents only records in its local SQLite database and private file store. It is not connected to AICTE or bank systems, does not verify documents as authentic, and does not replace any official process.

Operational dashboard metrics, workflow, document and relationship records, evidence checks, audit events, and priority queue entries come from the local API. Policy files and all sample data are illustrative and must be populated with synthetic values only.

## Implemented foundation and Phases 2–6

- FastAPI service with `GET /api/health`.
- Environment-based settings, SQLAlchemy SQLite engine, session dependency and local schema initialization.
- Consistent JSON error response for unhandled application errors and FastAPI validation errors.
- React, Vite, TypeScript and Tailwind responsive dashboard shell.
- SQLAlchemy models for institutions, institution-scoped FDR records, workflow-configuration snapshots, document requirements, and audit events.
- Validated, versioned JSON workflow configuration, transition enforcement, and successful/rejected transition audit events.
- Minimal institution, FDR-record, transition, workflow-configuration and record-audit APIs.
- Private multipart document storage with immutable document versions, upload-time SHA-256 digests, integrity checks, and evidence/audit records.
- Institution-scoped recorded FDR relationships and depth-bounded BFS/DFS exploration across FDRs, documents, versions, evidence checks, and lifecycle audit events.
- A structured synthetic relationship explorer in the dashboard; it does not display live backend data.
- Configurable explainable urgency scores and a database-sourced review queue rebuilt on each request.
- A Review Queue panel that reads live API data for the selected institution and shows explicit connection, loading, empty, and error states.
- A connected local FDR workspace for institution/record setup, workflow transitions, document version review, integrity checks, evidence, FDR relationships, graph traversal, and current priority scores.
- Argon2id password hashing, expiring server-side sessions in HttpOnly cookies, CSRF checks, login throttling, controlled first-admin bootstrap, forced temporary-password changes, account deactivation, and backend role/institution checks.
- System-admin account provisioning and institution membership assignment; institution-scoped record, document, evidence, relationship, audit, dashboard, and queue access.

OCR, tamper localization, bank APIs, malware scanning, policy approval workflow, and independent document-verification engines are not implemented. This prototype has not undergone independent security review and must not be exposed publicly.

## Architecture

FastAPI routes use Pydantic schemas, domain services, and SQLAlchemy sessions over SQLite. Workflow, upload, graph and priority policies are read from validated JSON. Account, membership, session, security-event, record, relationship, document/version, evidence-check, audit and score-calculation metadata are stored in SQLite. Document bytes are kept under the private storage root, outside the frontend tree, using generated random storage IDs. The dashboard and workspace read scoped local API data; all configured policy and demonstration content is illustrative. `VITE_DEPOSITGUARD_INSTITUTION_ID` optionally preselects an institution. Local schema creation uses SQLAlchemy `create_all`; a narrow additive compatibility step adds nullable upload-policy metadata columns to existing Phase 3 tables. A general-purpose migration framework is not implemented.

Only the local prototype database is an operational data source. No live government or financial-institution system is queried.

## Windows setup

Use two PowerShell terminals from the repository root.

### Backend

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python -m app.bootstrap_admin admin@example.local
uvicorn app.main:app --reload
```

The bootstrap command prompts for a display name and password twice using a no-echo password prompt. It creates the initial system administrator only if none exists. Do not put a real password in shell history. After signing in, create a synthetic institution in the Institutions page and provision users/assign roles from Settings. For newly provisioned users, provide the temporary password out of band; they must change it before using workspace APIs. Existing database contents are preserved; SQLAlchemy creates the additional auth tables without deleting records.

The API is at `http://localhost:8000`; interactive API docs are at `http://localhost:8000/docs`. Keep the frontend and API on the same hostname (`localhost`) so SameSite cookies work as configured. For HTTPS, set `AUTH_COOKIE_SECURE=true` and use matching HTTPS CORS origins.

Run backend tests from `backend` with:

```powershell
python -m pytest -q
```

### Frontend

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

Vite prints the local URL, usually `http://localhost:5173`. The frontend environment file uses `VITE_API_BASE_URL` (default `http://localhost:8000`) and optional `VITE_DEPOSITGUARD_INSTITUTION_ID`. The latter preselects an institution the user is authorized to access; it is not required because the UI can list and select accessible institutions. Restart Vite after changing `.env.local`.

Create and check the production bundle with:

```powershell
npm run build
```

## Configuration

Copy `backend/.env.example` to `backend/.env` and adjust local runtime settings as needed. Do not put secrets in source control. Environment variables configure the app title, API prefix, database URL, CORS origins (as a JSON array), `WORKFLOW_CONFIG_PATH`, `UPLOAD_POLICY_PATH`, `GRAPH_POLICY_PATH`, `PRIORITY_POLICY_PATH`, and `PRIVATE_STORAGE_PATH`.

### Local authentication and permissions

Sessions use an opaque random token whose SHA-256 hash is stored in SQLite; the browser cookie is HttpOnly, SameSite=Strict, and expires according to `AUTH_SESSION_MINUTES` (5–720 minutes). A second CSRF cookie is paired with an `X-CSRF-Token` header for mutations. Passwords use Argon2id. Ten failed sign-ins for the same normalized email and remote address in a 15-minute window are throttled. Changing a password revokes other sessions; deactivation and password reset revoke all existing sessions. Temporary passwords must be changed before any workspace API is available.

Permissions are enforced by FastAPI from the authenticated account and persisted membership, not from frontend visibility. System administrators can provision users, reset passwords, deactivate accounts, assign roles, and create institutions. Institution administrators can create FDR records and perform permitted workflow operations. Document officers can upload and run integrity checks. Reviewers can inspect data, request configured clarification stages, create configured relationships, and run checks. Approvers can transition only to configured decision stages and run checks. Auditors have read-only access. All roles are institution-scoped; system administrators have an explicit global scope. This prototype does not implement institution-admin user management, per-record assignment, MFA, self-service recovery, SSO, or tamper-proof audit storage. Bootstrap commands do not store the password in the project.

### Workflow and document-requirement configuration

The default file is `backend/config/workflow.json`. Its states and transitions are explicitly illustrative local-development examples, not AICTE stages, requirements, or policy. The application reloads and validates this file for each workflow-configuration read, record creation, and transition request. A relative `WORKFLOW_CONFIG_PATH` is resolved from the backend directory. Invalid or missing configuration fails closed with HTTP 503; it never permits a transition by default.

The configuration validator checks required fields, unique stage and requirement keys, the initial-stage reference, unique transitions, transition endpoints, and self-transitions. To change behavior, edit the JSON file and assign a new `version` whenever its contents change. Versions are immutable: SQLite stores a canonical SHA-256 content fingerprint and a configuration snapshot, while each record-creation/transition audit event records the applied version. Reusing a version string with changed content is rejected. Configured document requirements are also copied into version-linked `document_requirements` rows; Phase 2 records them but does not yet enforce document completeness.

The database models do not assume FDR references are globally unique. An optional instrument reference is indexed with its institution ID, but not made unique. Sensitive bank fields and real institution records are intentionally absent from this prototype.

### Upload policy, storage and integrity results

The default upload policy is `backend/config/uploads.json`; it can be moved with `UPLOAD_POLICY_PATH`. The private file root defaults to `backend/private_uploads` and can be changed with `PRIVATE_STORAGE_PATH`. Relative paths resolve from the backend directory. The application refuses a storage root inside the frontend directory tree. On Windows the directory inherits the current account's filesystem ACL; deployment-specific ACL hardening is still required.

The example policy allows PDF, PNG and JPEG files and sets a 10 MiB per-file maximum. The maximum is configurable up to a 100 MiB safety ceiling. The policy has a version; once used, its content is immutable under that version. Changed content requires a new version. File acceptance requires an allowed filename extension, a compatible declared media type (or generic `application/octet-stream`), and matching format-specific content/structure checks. These checks are not a malware scan or a full document parser. Files are streamed into a private staging folder, size-checked while reading, validated, moved to a generated identifier, and hashed from the stored bytes. The original filename is kept only as normalized display metadata; it is never a storage path.

An upload category must exist in the active workflow configuration's `document_requirements`; this keeps category names configurable. The example category is explicitly illustrative, not an AICTE requirement. A `document_id` form field can be supplied to add a new immutable version to an existing logical document. Without it, the upload creates a new logical document. A failed database write triggers best-effort removal of the newly stored file; filesystem and SQLite transactions cannot be made fully atomic, so a process crash can leave an orphaned private file.

Integrity results use three statuses: `PASS` means the current stored bytes match the upload-time SHA-256; `FAIL` means they differ; `INDETERMINATE` means the file could not be read or was missing. Every executed check is saved against the exact document-version ID with the recorded and observed digest, explanation, software/upload-policy versions and evidence reference. A digest match establishes byte consistency only; a mismatch indicates changed bytes relative to the recorded digest, not fraud or proof of authenticity. The original digest is never changed by a check.

### Phase 4 relationship graph

The default validated graph policy is `backend/config/graph.json` and can be moved with `GRAPH_POLICY_PATH`. It defines supported FDR relationship types and labels, which types permit cycles, the maximum traversal depth (6), and the maximum returned node count (500). Queries load neighbors incrementally from SQLite instead of loading the entire database. Results are marked `truncated` if they reach the node limit.

The `fdr_relationships` table stores explicit directed FDR-to-FDR associations with institution scope, configured type, actor reference, note, and review status. Existing foreign keys are reused for FDR/document, document/version, and version/evidence links; FDR audit events are surfaced as lifecycle nodes. `renewal_of` and `replacement_of` are directional lifecycle links and reject a directed cycle of their own type. `related_to` is a general association and permits cycles. BFS and DFS traverse visible graph links in either direction, use a visited set to prevent repeats, and return discovery paths with depth and edge metadata. Each edge is a recorded association, not a verified fact. Review status can be `unreviewed` or `requires_review`; this phase does not establish authenticity, validity, or fraud.

### Phase 5 urgency scoring and queue

The validated, illustrative policy is `backend/config/priority.json`, configurable through `PRIORITY_POLICY_PATH`. It defines the eligible workflow stages, factor behavior and point contributions, and category thresholds. Current factors are missing configured required document categories, latest SHA-256 check per document version (`FAIL`/`INDETERMINATE`, or an explicit no-check contribution), clarification stages, and elapsed time in configured review stages. The policy's example values are local demonstration values, not official deadlines, weights, or AICTE priority categories. The active workflow configuration supplies the illustrative stage and document-requirement names. There is no deadline field in the current FDR model, so deadline scoring is not performed; each result reports that missing input.

The score is the sum of configured factor contributions capped at 100; the highest configured category threshold not above the score supplies the category. Each factor returns its points, evaluation state, explanation, and missing inputs. Scores are advisory and do not indicate fraud, document validity, or approval. Reusing a priority policy version with changed content is rejected after that version has been used; change the version when editing its contents.

`review_priority_calculations` stores timestamped score snapshots including policy version and SHA-256 fingerprint. These snapshots are history, not queue state. Every queue request queries currently eligible records from SQLite, recalculates their scores from current inputs, and orders them with `heapq`: descending score, then oldest workflow update, oldest creation time, and record ID. Duplicate record IDs are removed before heap insertion. Completed or otherwise ineligible stages are excluded. This local implementation recalculates eligible records on every request; it is not a production-scale scheduler or cached queue.

The frontend reads institutions from the local API when no ID is configured and requires the user to select one; it never invents an institution ID. To preselect a known local institution, set `VITE_DEPOSITGUARD_INSTITUTION_ID` in `frontend/.env.local`. The Review Queue shows disconnected, loading, empty, and API error states. Existing Overview metrics and activity remain explicitly synthetic demo content.

### Demonstrate the connected workflow

1. Start the backend and frontend using the Windows commands above. Open the Vite URL and wait for the institution list to load from the API.
2. Enter a clearly synthetic actor label, create a local institution if none exists, and select it. The backend creates the institution ID.
3. Create an FDR record with an optional synthetic instrument reference, select it, and move it from `draft` to `submitted` using the configured transition control.
4. Create a local test file and upload it under a configured document category:

   ```powershell
   Set-Content -Path .\synthetic-evidence.pdf -Value "%PDF-1.4`nSynthetic DepositGuard test fixture`n%%EOF" -NoNewline -Encoding ascii
   ```

5. Run “Check integrity” on the uploaded version. Inspect the distinct `PASS`, `FAIL`, or `INDETERMINATE` evidence entry and its explanation. `PASS` means only that the stored bytes match the upload-time SHA-256.
6. Create a second FDR record in the same institution, record a configured relationship from the first record, and inspect the live BFS/DFS graph. Edge arrows show stored source-to-target direction.
7. Review the record's current advisory score and factor explanations, then inspect the institution's live Review Queue. Priority values come from the local illustrative policy and do not approve or verify a record.

### Live data and illustrative content

- **Live local API data:** institution list/create, FDR record list/create/detail, workflow transitions and audit history, uploads and immutable versions, integrity checks and evidence history, relationship creation/listing, graph traversal, urgency scores, and priority queue. These are records stored in the configured local SQLite database and private file root.
- **Illustrative only:** Overview metrics, Overview activity, and the relationship preview shown before selecting an institution. These are labeled synthetic and are not treated as backend records. No AICTE portal or bank integration exists.
- **API unavailable:** the workspace and panels show an error or disconnected state; the UI does not replace failed live requests with synthetic record rows.

### Phase 2 API

All routes use the `/api` prefix by default. Create requests accept only declared schema fields; record IDs, institution ownership, workflow stage, timestamps and audit events are controlled by the backend.

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/workflow/configuration` | Read the currently validated workflow definition. |
| `GET` | `/api/institutions` | List local institutions (limit 1–500). |
| `POST` | `/api/institutions` | Create a local institution and its creation audit event. |
| `GET` | `/api/institutions/{institution_id}/fdr-records` | List records scoped to an existing institution (limit 1–500). |
| `POST` | `/api/institutions/{institution_id}/fdr-records` | Create a record at the configured initial stage. |
| `GET` | `/api/institutions/{institution_id}/fdr-records/{record_id}` | Read a record within its institution scope. |
| `POST` | `/api/institutions/{institution_id}/fdr-records/{record_id}/transitions` | Request a configured transition; returns `409` if disallowed. |
| `GET` | `/api/institutions/{institution_id}/fdr-records/{record_id}/audit-events` | Read record-scoped audit history, newest first. |
| `POST` | `/api/institutions/{institution_id}/fdr-records/{record_id}/documents` | Multipart upload with `file`, `category_key`, `actor_id`, and optional `document_id` to add a version. |
| `GET` | `/api/institutions/{institution_id}/fdr-records/{record_id}/documents` | List documents and latest version metadata. |
| `GET` | `/api/institutions/{institution_id}/fdr-records/{record_id}/documents/{document_id}/versions` | List immutable versions and their recorded digests. |
| `POST` | `/api/institutions/{institution_id}/fdr-records/{record_id}/documents/{document_id}/versions/{version_id}/integrity-checks` | Recompute SHA-256 and persist an evidence result; JSON body includes `actor_id`. |
| `GET` | `/api/institutions/{institution_id}/fdr-records/{record_id}/evidence-checks` | Read evidence/check history, newest first. |

### Phase 4 graph API

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/graph/policy` | Return validated graph relationship types for client forms. |
| `POST` | `/api/institutions/{institution_id}/fdr-records/{record_id}/relationships` | Record a configured association to a same-institution FDR record. |
| `GET` | `/api/institutions/{institution_id}/fdr-records/{record_id}/relationships` | List direct FDR relationships (limit 1–500). |
| `GET` | `/api/institutions/{institution_id}/fdr-records/{record_id}/graph` | Explore the connected graph; `algorithm=BFS|DFS` and optional `max_depth`. |
| `GET` | `/api/institutions/{institution_id}/fdr-records/{record_id}/graph/bfs` | Explicit breadth-first traversal. |
| `GET` | `/api/institutions/{institution_id}/fdr-records/{record_id}/graph/dfs` | Explicit depth-first traversal. |

All graph operations scope queries to the authenticated user's requested institution. Membership checks apply before route handling and graph queries additionally constrain every traversed entity to the same institution. The selected-record graph explorer uses these endpoints.

### Phase 5 priority API

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/review-priority/policy` | Return the validated active policy and canonical content fingerprint. |
| `GET` | `/api/institutions/{institution_id}/fdr-records/{record_id}/urgency-score` | Calculate and persist a current explainable score for one institution-scoped record. |
| `GET` | `/api/institutions/{institution_id}/review-priority-queue` | Recalculate and return eligible records in priority order; supports `limit` 1–500. |

The queue returns workflow stage, score, category, factor explanations, missing inputs, policy fingerprint, calculation time, and a null deadline where none is stored. Queries are institution-scoped, but the supplied institution ID is not authorization.

Legacy write schemas still accept an `actor_id` field for compatibility with earlier clients, but route handlers ignore that field and derive the recorded actor from the authenticated server-side user. Rejected workflow transitions are written as audit events and do not alter the record stage. Invalid configuration errors return `503`; disallowed uploads return `413` when oversized or `415` for invalid/disallowed media; resources outside the caller's institution scope return `404`.

**Implemented local-prototype access controls:** private routes require a valid server-side session cookie. Institution membership and role checks run in the backend; cross-institution resource access is concealed with `404`. Mutating requests require CSRF cookie/header agreement and an allowed Origin when supplied. The initial administrator is provisioned by a local interactive command; there is no public signup. `AUTH_COOKIE_SECURE` defaults to `false` only for localhost HTTP development and must be enabled for HTTPS. Keep frontend and API on the same hostname so SameSite cookies are sent consistently. These controls have automated tests but have not been independently security reviewed; do not expose the unauthenticated development server publicly. Audit and security-event records are ordinary SQLite rows and are not tamper-proof. There is no malware scanning, configured encryption-at-rest, document download API, retention/deletion workflow, general migration framework, or production storage hardening. Use only synthetic identifiers and data.

The system-admin role alone provisions/deactivates users, resets passwords, assigns memberships, and reads security events. Institution administrators can manage authorized FDR workflow operations but cannot provision accounts in this implementation; institutional self-service administration remains unavailable. Reviewers may request only configured clarification stages, approvers may transition only to configured decision stages, and auditors are read-only. The backend enforces temporary-password changes, account activation, session expiry/revocation, and rate-limited sign-in attempts. Local authentication is not a substitute for deployment review, independent security testing, hardened secret management, or institution-specific operations.

## Dependency versions

Verified with Python 3.11.9, Node.js 24.11.1 and npm 11.19.0.

| Layer | Installed versions |
| --- | --- |
| Backend | FastAPI 0.115.12, Uvicorn 0.34.2, SQLAlchemy 2.0.41, pydantic-settings 2.9.1, HTTPX 0.28.1, pytest 8.3.5, python-multipart 0.0.32 |
| Frontend | React 19.3.1, Vite 6.4.5, TypeScript 5.7.3, Tailwind CSS 4.3.3, `@tailwindcss/vite` 4.3.3 |

The backend versions are pinned in `backend/requirements.txt`. Frontend versions are pinned in `frontend/package.json` and resolved exactly in `frontend/package-lock.json`. Use the lockfile with `npm ci` for a reproducible install. If pip reports the machine's missing `CURL_CA_BUNDLE` path (`C:\Program Files\PostgreSQL\18\ssl\certs\ca-bundle.crt`), clear that invalid override in the current PowerShell session with `$env:CURL_CA_BUNDLE = ""` and retry installation.

## Later phases

Potential later work includes institution-admin user management, general database migrations, malware scanning, document retention/deletion, document-requirement enforcement, OCR/other checks, lifecycle reminders, and a dossier. Any simulated or unavailable verification must remain visibly distinct from live-authorised confirmation. SHA-256 can detect changes relative to a recorded file digest; it cannot prove that an original document is genuine. Workflow, upload, graph, priority and sample content remain explicitly synthetic/illustrative.
