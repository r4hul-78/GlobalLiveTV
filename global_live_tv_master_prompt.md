# MASTER PROMPT: GLOBAL LIVE TV PLATFORM

## Project Overview

Build a complete, modern web application that allows users to discover, search, filter, and watch publicly available television streams that are legally permitted to be listed or embedded.

The application will collect channel metadata from the open-source `iptv-org/iptv` repository, store it in a database, expose it through a Python backend, and play compatible streams directly inside the browser.

The application must prioritize reliability, security, usability, maintainability, and honest reporting of channel availability.

# GLOBAL DEVELOPMENT RULES

Follow these rules throughout every development phase.

1. Inspect the existing workspace before creating, modifying, or deleting files.
2. Implement the project in the nine steps listed below, in order.
3. On the first execution, implement Step 1 only. Never automatically implement all nine steps.
4. After completing each step, execute its relevant tests, report the results, and stop until I explicitly authorize the next step.
5. Create and modify actual project files. Do not merely output code snippets or claim that implementation is complete without verifying it.
6. Use sensible engineering judgment. Ask questions only when a genuinely blocking decision requires clarification.
7. Preserve existing working code and avoid unnecessary rewrites.
8. Never fabricate channel metadata, test results, stream availability, or successful playback.
9. Do not bypass DRM, authentication, subscription requirements, geographic restrictions, or other access controls. Public listing does not automatically establish legal authorization.
10. Never proxy or re-host live media through the Flask server. The browser must connect directly to the authorized stream URL.
11. Validate external URLs, redirects, and resolved IP addresses to prevent SSRF and access to prohibited internal or private network destinations.
12. Do not expose secrets, stack traces, internal paths, or sensitive operational information through public APIs.
13. Handle missing metadata, malformed playlists, broken streams, external service outages, and temporary network failures gracefully.
14. Keep background ingestion and health-checking jobs separate from normal web requests and Flask web workers.
15. Maintain accurate documentation throughout development.
16. Use actual automated tests and report failures honestly.
17. Do not proceed to the next step without my explicit instruction.

# TECHNOLOGY STACK

**Frontend**

- HTML5
- CSS3
- Vanilla JavaScript

**Backend**

- Python 3
- Flask
- SQLAlchemy

**Database**

- SQLite for the initial version
- Configurable database URL to support future PostgreSQL deployment

**Video player**

- HTML5 video element
- HLS.js using a stable, explicitly pinned version
- Native HLS fallback where supported

**Data source**

- Public playlists from `iptv-org/iptv`

**Testing**

- pytest
- Flask test client

Do not introduce React, Vue, Angular, Node.js, Django, or unnecessary frameworks.

---

# STEP 1 — PROJECT FOUNDATION

## Objective

Create a clean, modular, working Flask application foundation.

## Tasks

1. Inspect the current workspace and identify any existing project files. Create all the required markdown files required for this project development. Such as PROJECT_CONTEXT.md, ARCHITECTURE.md, AGENT.md, TESTING.md, DEBUG.md, DEVELOPMENT.md, etc files.
2. Set up Flask using the application factory pattern.
3. Configure SQLAlchemy and SQLite.
4. Support environment-based configuration, including a configurable database URL.
5. Create a modular project structure:

   - `app/__init__.py`
   - `app/config.py`
   - `app/models/`
   - `app/routes/`
   - `app/services/`
   - `app/jobs/`
   - `app/templates/`
   - `app/static/css/`
   - `app/static/js/`
   - `scripts/`
   - `tests/`
   - `run.py`
   - `requirements.txt`
   - `.env.example`
   - `.gitignore`
   - `README.md`

6. Add centralized configuration, logging, error handling, and basic application-health infrastructure.
7. Create a minimal landing page to verify template rendering and static asset delivery.
8. Add a Python virtual-environment setup workflow.
9. Add pytest configuration and an initial application startup test.
10. Ensure local databases, `.env` files, logs, virtual environments, and generated artifacts are excluded from Git.

## Acceptance criteria

- Flask starts successfully.
- The landing page loads.
- Static assets are served correctly.
- The initial automated test passes.
- Setup instructions are documented.

**STOP after Step 1. Report completed work, files changed, commands executed, test results, and known issues. Wait for my approval.**

---

# STEP 2 — DATABASE MODELS AND IPTV INGESTION

## Objective

Implement the database schema and automated playlist importer.

## Database models

Create suitable SQLAlchemy models for:

### Channel

- Internal ID
- External channel ID when available
- Channel name
- Logo URL
- Direct stream URL
- Country code and country name when known
- Language when known
- Active/listed status
- First-seen and last-updated timestamps
- Latest health status and last-check timestamp

### Country

- Standard country code
- Display name

### Genre

- Stable category identifier
- Display name

### Language

- Standard language code
- Display name

### StreamCheck

- Channel reference
- Check timestamp
- Outcome
- HTTP status when available
- Response time when available
- Concise diagnostic reason

Establish appropriate relationships, constraints, and indexes. Avoid unnecessary duplication.

## Playlist ingestion

Use configurable URLs for the published `iptv-org/iptv` playlists, including:

- `https://iptv-org.github.io/iptv/index.m3u`
- `https://iptv-org.github.io/iptv/index.country.m3u`
- `https://iptv-org.github.io/iptv/index.category.m3u`
- `https://iptv-org.github.io/iptv/index.language.m3u`

Handle source outages gracefully. Do not assume all playlists contain identical metadata.

## Parser requirements

1. Parse M3U and EXTINF records, including quoted attributes and the stream URL following each record.
2. Extract `tvg-id`, `tvg-name`, `tvg-logo`, and `group-title` when present.
3. Enrich country, category, and language metadata from appropriate source playlists.
4. Handle commas in channel names, missing attributes, malformed records, inconsistent line endings, and duplicate entries.
5. Prefer authoritative channel identifiers when matching records.
6. Never guess unknown metadata or merge uncertain records blindly.
7. Validate source URLs and reject unsupported or unsafe destinations.
8. Implement idempotent database upserts so repeated imports do not create duplicates.
9. Preserve valid catalog data when a source download or partial import fails.
10. Support dry-run mode and an optional record limit.
11. Log imported records, updated records, skipped entries, and errors.
12. Do not present hardcoded demonstration channels as genuine imported records.

## Acceptance criteria

- Parser tests cover valid and malformed playlists.
- Missing metadata is handled correctly.
- Repeated imports do not produce duplicates.
- Database relationships work correctly.
- Failed downloads do not destroy existing catalog data.

**STOP after Step 2 and report the ingestion implementation and test results.**

---

# STEP 3 — STREAM HEALTH-CHECKING ENGINE

## Objective

Create a separate service that assesses whether external streams appear accessible without downloading entire broadcasts.

## Requirements

1. Validate every candidate URL before making a network request.
2. Reject localhost, private, loopback, link-local, multicast, reserved, and other prohibited destinations.
3. Validate DNS-resolved addresses and redirect destinations to prevent SSRF and DNS-rebinding bypasses.
4. Use strict connection/read timeouts, bounded response sizes, limited retries, and configurable concurrency.
5. Inspect HTTP responses and recognizable HLS manifest content instead of treating HTTP 200 as proof of playback.
6. When practical, inspect a small portion of a referenced media playlist or segment.
7. Do not download continuous media streams.
8. Resolve relative HLS resource URLs safely and validate destinations before requesting them.
9. Record health outcomes using consistent statuses:
   - `unknown`
   - `healthy`
   - `degraded`
   - `unavailable`
   - `unsupported`
10. Track the latest check, last successful check, consecutive failure count, response time, and concise diagnostic reason.
11. Do not permanently mark a channel unavailable after one timeout or temporary error.
12. Run checks in bounded batches outside normal API requests.
13. Never allow public API users to submit arbitrary URLs for backend fetching.

## Acceptance criteria

Test valid-looking manifests, invalid content, timeouts, failed requests, redirects, unsafe destinations, and repeated failures.

Document that successful manifest/segment checks cannot guarantee uninterrupted playback in every browser.

**STOP after Step 3.**

---

# STEP 4 — FLASK REST API

## Objective

Expose catalog information through a reliable JSON API.

Implement these endpoints.

### GET `/api/channels`

Support:

- `q`: channel-name search
- `country`: country code
- `genre`: category identifier
- `language`: language code
- `status`: optional stream-health filter
- `page`: page number
- `per_page`: page size

### GET `/api/channels/<id>`

Return publicly appropriate metadata for a single channel.

### GET `/api/filters`

Return available countries, genres, and languages based on the actual catalog.

### GET `/api/health`

Return a minimal application-health response without exposing sensitive diagnostics.

## API requirements

1. Query the database using SQLAlchemy.
2. Apply combined filters correctly.
3. Normalize search and filter inputs consistently.
4. Validate query parameters and impose a maximum page size.
5. Return pagination metadata and total result counts.
6. Use deterministic sorting.
7. Return only necessary fields.
8. Handle invalid parameters, missing records, empty results, and database failures cleanly.
9. Avoid indefinitely caching stale filter metadata.
10. Add automated tests for every endpoint.

## Acceptance criteria

Verify search, country filtering, genre filtering, combined filters, pagination, invalid input, and empty results.

**STOP after Step 4.**

---

# STEP 5 — RESPONSIVE CHANNEL DISCOVERY UI

## Objective

Build a polished streaming-directory interface using HTML, CSS, and vanilla JavaScript.

## Visual direction

Create a modern, minimal media-discovery experience with:

- Strong typography
- Consistent spacing
- Refined channel cards
- Subtle borders and hover states
- A coherent color system
- Responsive desktop, tablet, and mobile layouts
- Clear loading and error states

Avoid unnecessary animation, visual clutter, and oversized controls.

## Required interface components

1. Header and application branding.
2. Prominent search bar.
3. Country filter.
4. Genre filter.
5. Optional language filter.
6. Clear-filters action.
7. Result count and pagination.
8. Responsive channel grid.
9. Channel cards displaying logos, names, available country flags, country names, and genres.
10. Optional health indicators using accurate and understandable labels.
11. Loading skeletons or equivalent indicators.
12. Empty-result, failed-request, and missing-logo states.

## Frontend behavior

- Fetch real catalog data from the Flask API.
- Update results without a full-page reload.
- Debounce search input.
- Prevent stale requests from overwriting newer results.
- Preserve active filters while changing pages.
- Safely render external metadata using DOM methods and `textContent`.
- Validate external URLs.
- Handle failed logos with visual fallbacks.
- Lazy-load images where practical.
- Support keyboard navigation, visible focus, proper labels, and adequate contrast.

Do not hardcode demo channels as live results.

## Acceptance criteria

Test all filters, combined searches, pagination, clearing filters, loading states, failed API requests, broken logos, and responsive layouts.

**STOP after Step 5.**

---

# STEP 6 — HLS VIDEO PLAYER

## Objective

Play compatible television streams directly in the browser.

## Player interface

Create a responsive player panel, modal, or dedicated view containing:

- Video player
- Channel name and logo
- Country and available category
- Loading indicator
- Playback error message
- Retry action
- Close/back action

Keep the player visually consistent with the discovery interface.

## Playback requirements

1. Use an HTML5 video element and a stable, pinned HLS.js release.
2. Detect HLS.js compatibility using documented library methods.
3. Use native HLS playback where the browser supports it.
4. Initialize playback from the selected channel's stored stream URL.
5. Handle manifest loading, media attachment, playback failures, and fatal HLS.js errors.
6. Show understandable errors for unavailable streams, incompatible formats, CORS failures, and inaccessible resources.
7. Respect browser autoplay restrictions.
8. Explain when playback cannot start because of browser policies.
9. Destroy old HLS.js instances and release media resources when switching channels or closing the player.
10. Prevent duplicated event listeners, multiple player instances, and memory leaks.
11. Provide a controlled retry mechanism.
12. Do not proxy media through Flask or bypass source restrictions.

Use an authorized demonstration HLS stream for development and testing where feasible.

## Acceptance criteria

Verify playback of a suitable demonstration stream in a compatible browser. Also test broken URLs, failed playback, retry behavior, channel switching, and cleanup.

A successful demonstration stream must not be treated as proof that all catalog streams are playable.

**STOP after Step 6.**

---

# STEP 7 — FULL APPLICATION INTEGRATION

## Objective

Connect the ingestion service, database, REST API, frontend, and player into a coherent application.

## Requirements

1. Connect channel selection to the correct player.
2. Keep search, filters, pagination, selected channel, and playback state synchronized.
3. Preserve filters when the player closes.
4. Centralize frontend request and error-handling utilities.
5. Handle missing logos, incomplete metadata, stale health results, and unavailable sources gracefully.
6. Provide consistent loading, empty, and error states.
7. Safely render all external metadata.
8. Ensure keyboard interactions and accessible dynamic status announcements.
9. Provide source attribution and explain that stream availability depends on external providers.
10. Provide a simple channel issue-reporting mechanism without unnecessarily collecting personal information.
11. Do not add accounts, payments, unnecessary tracking, or unrelated functionality.

## Acceptance criteria

Complete an end-to-end user journey:

- Open the website.
- Search for a channel.
- Apply country and genre filters.
- Navigate through results.
- Select a channel.
- Attempt playback.
- Handle a broken or blocked stream.
- Retry or close the player.
- Resume browsing with the previous filters intact.

**STOP after Step 7.**

---

# STEP 8 — AUTOMATED REFRESH AND PERFORMANCE

## Objective

Keep channel metadata and health information reasonably current while maintaining application reliability.

## Requirements

1. Provide separate commands for playlist ingestion and health checking.
2. Make both commands safe to rerun.
3. Configure refresh intervals, timeouts, concurrency, and batch sizes.
4. Run scheduled work outside Flask web workers.
5. Prevent overlapping refresh jobs and duplicate workers.
6. Record import summaries, job failures, and completion timestamps.
7. Preserve the last valid catalog when external sources fail.
8. Retain temporarily unavailable channels for future recovery.
9. Process records incrementally.
10. Add useful database indexes and caching where justified.
11. Keep normal API requests independent of complete ingestion and health-check runs.
12. Document scheduling using an operating-system scheduler, deployment scheduler, or suitable alternative.
13. Never claim background scheduling is active merely because the command exists.

## Reliability checks

- Bound all network activity.
- Avoid overloading external stream servers.
- Ensure logs do not expose secrets.
- Keep database queries efficient as the catalog grows.
- Preserve normal browsing when data sources are unavailable.

## Acceptance criteria

Execute repeated ingestion and health-check runs. Confirm there are no duplicate records, accidental catalog deletions, overlapping workers, or unnecessary delays to API requests.

**STOP after Step 8.**

---

# STEP 9 — FINAL AUDIT AND RELEASE READINESS

## Objective

Test the complete application and prepare reliable documentation for deployment.

## Backend testing

Verify:

- Playlist parsing and metadata enrichment
- Duplicate handling and idempotent imports
- Database constraints and relationships
- API search and filtering
- Pagination and invalid parameters
- Health-check timeouts and repeated failures
- SSRF and redirect protections
- External source failures
- Empty catalogs and missing metadata
- Configuration and database errors

## Frontend and playback testing

Verify:

- Desktop, tablet, and mobile layouts
- Search and combined filters
- Pagination and filter persistence
- Missing and broken logos
- Loading, empty, and error states
- Player initialization and cleanup
- Working, unavailable, and unsupported streams
- Keyboard navigation and visible focus
- Browser console and network errors

## Complete README documentation

Include:

1. Project overview.
2. Architecture and data flow.
3. Prerequisites.
4. Installation and virtual-environment setup.
5. Environment configuration.
6. Database initialization.
7. Starting the Flask application.
8. Running ingestion.
9. Running health checks.
10. Scheduling refresh jobs.
11. Running automated tests.
12. Deployment instructions.
13. Known limitations.
14. Source attribution and usage considerations.
15. Channel-reporting procedures.

## Release acceptance criteria

The application is ready for its first release when:

- It starts using documented instructions.
- The catalog imports from configured playlists.
- Repeated imports do not create duplicates.
- Search, country filters, genre filters, and pagination work.
- The frontend displays real database records.
- A compatible HLS stream plays in a supported browser.
- Playback failures are handled gracefully.
- Health checking runs outside normal web requests.
- Unsafe destinations are rejected.
- Automated tests pass, or outstanding failures are documented.
- Core functionality is usable and no known critical defects are ignored.
- Legal authorization and stream availability are not overstated.

Produce a final report containing implemented features, actual test results, unresolved defects, security considerations, configuration requirements, and deployment readiness.

**STOP after Step 9.**

---

# REQUIRED REPORT AFTER EACH STEP

After completing each step, provide:

1. **Completed:** Features implemented.
2. **Files changed:** Files created or modified.
3. **Validation:** Commands executed and their actual results.
4. **Known issues:** Remaining defects and limitations.
5. **Next step:** What the next phase will implement.

Do not proceed until I explicitly authorize the next step.

# START NOW

Inspect the existing workspace and execute **STEP 1 — PROJECT FOUNDATION only**. Implement the files, run the relevant checks, report the results, and wait for my instruction before proceeding to Step 2.
