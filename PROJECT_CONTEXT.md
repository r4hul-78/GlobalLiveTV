# PROJECT CONTEXT: GLOBAL LIVE TV PLATFORM

## 1. Project Purpose & Vision
The **Global Live TV Platform** is a modern, responsive web application that enables users to discover, search, filter, and stream publicly available television channels from around the world that are legally permitted to be listed and viewed.

The project aggregates channel metadata from the community-maintained [iptv-org/iptv](https://github.com/iptv-org/iptv) repositories, normalizes and stores the data in a relational database, exposes high-performance REST APIs, and provides an elegant browser-based playback experience using standard HTML5 Video and pinned HLS.js.

---

## 2. Core Architectural Principles
1. **Direct Stream Delivery (No Media Proxying)**:
   - The Flask backend never re-hosts, caches, or proxies live video streams.
   - The user's browser establishes direct streaming connections with external stream servers.
2. **Robust Security & SSRF Protection**:
   - Backend validation strictly prohibits querying internal, private, loopback, link-local, multicast, or reserved IP ranges.
   - DNS resolution and redirects are strictly inspected to prevent DNS rebinding attacks.
3. **Honest Availability Reporting**:
   - Streams are not marked as online simply because an HTTP 200 was received; manifest syntax and segment references are verified.
   - Stream health is clearly reported (`healthy`, `degraded`, `unavailable`, `unsupported`, `unknown`).
4. **Decoupled Background Tasks**:
   - Ingestion and periodic health checking run as standalone background jobs or CLI commands, completely decoupled from Flask web workers to avoid blocking user traffic.
5. **Zero Heavy Framework Clutter**:
   - Frontend is built with Vanilla HTML5, CSS3, and JavaScript—fast, clean, accessible, and lightweight.
   - Backend relies on Flask and SQLAlchemy with zero unnecessary overhead.

---

## 3. Technology Stack Overview
| Layer | Technology | Rationale |
|---|---|---|
| **Language** | Python 3 | Clean, robust ecosystem for data parsing and web serving. |
| **Backend Framework** | Flask | Lightweight, application factory pattern, modular blueprints. |
| **ORM / Database** | SQLAlchemy & SQLite (PostgreSQL compatible) | Structured schemas, relationships, indexing, with portability. |
| **Frontend UI** | HTML5, Modern CSS3, Vanilla JS | High performance, no bulky bundler dependencies, pure web standards. |
| **Video Playback** | HLS.js (explicitly pinned) & Native HLS | Reliable cross-browser HLS playback with fallback for Safari. |
| **Test Suite** | pytest & Flask Test Client | Rapid, reproducible automated testing. |

---

## 4. Nine-Step Development Roadmap
- [x] **Step 1 — Project Foundation** (Completed: Modular setup, application factory, config, logging, health check, minimal UI, test suite)
- [x] **Step 2 — Database Models & IPTV Ingestion** (Completed: SQLAlchemy schema, M3U/EXTINF parser, SSRF defense, idempotent upserts)
- [x] **Step 3 — Stream Health-Checking Engine** (Completed: Safe HTTP probes, SSRF defense, HLS manifest validation, failure progression)
- [x] **Step 4 — Flask REST API** (Completed: Channels catalog, taxonomy filtering, search, dynamic filters, health status, and deterministic pagination)
- [x] **Step 5 — Responsive Channel Discovery UI** (Completed: Live catalog directory, debounced search, dynamic taxonomy filters, responsive cards, image fallbacks, and details modal)
- [x] **Step 6 — HLS Video Player** (Completed: Pinned HLS.js v1.5.17, Safari native fallback, autoplay restriction handling, controlled error recovery, and theater modal)
- [x] **Step 7 — Full Application Integration** (Completed: Bidirectional URL sync, deep linking, browser history navigation, anonymous issue reporting, and accessible dynamic announcements)
- [x] **Step 8 — Automated Refresh & Performance** (Completed: Process concurrency JobLock, stale lock recovery, JobRun auditing, composite database indexes, in-memory filter TTL caching, unified refresh runner, and scheduler documentation)
- [x] **Step 9 — Final Audit & Release Readiness** (Completed: 101 automated pytest tests passing, end-to-end user journeys, comprehensive SSRF test matrix, browser UI and player validation, and complete 15-section production README)

---

## 5. Release Readiness Status
- **Automated Tests**: 101/101 passing (100% success rate across 8 test modules)
- **Frontend / Player**: Verified in Chrome browser (discovery, filters, player modal, issue dialog, clean console)
- **Security**: SSRF protection, DNS rebinding mitigation, no media proxying, anonymous privacy-first issue reporting
- **Documentation**: 15 required sections in README.md, comprehensive ARCHITECTURE.md, TESTING.md, DEBUG.md, DEVELOPMENT.md
s