# Career Intelligence Platform — Master Implementation Plan for Codex

## 1. Project Objective

Build a production-quality, generic, extensible Career Intelligence Platform.

The system must allow registered users to:

1. Enter a company name, website URL, or careers-page URL.
2. Automatically discover the company's official career website.
3. Search and extract available job vacancies.
4. Configure job-matching preferences, including skills, keywords, location, experience, employment type, and exclusions.
5. Match discovered jobs against user preferences.
6. Display match percentages with understandable explanations.
7. Save company searches and view scan results.
8. View successful, failed, incomplete, and unsupported scan results.

The architecture must support future enhancements such as scheduled scans, job notifications, resume analysis, and assisted job applications.

These future features must not be implemented during the initial MVP unless explicitly approved.

## 2. Mandatory Technology Stack

**Backend**
- Python 3.13, subject to dependency compatibility verification
- FastAPI
- Pydantic v2
- SQLAlchemy 2 with async support
- Alembic
- PostgreSQL 17
- HTTPX
- Celery and Redis when asynchronous scanning is introduced
- Python Playwright for JavaScript-rendered career websites

**Frontend**
- Angular, using a compatible stable version verified at implementation time
- TypeScript with strict mode
- Angular standalone components
- Angular Router
- Reactive Forms
- SCSS

**AI**
- OpenRouter as the first AI provider
- Provider-independent AI interface
- Configurable model, API key, provider and timeout
- Deterministic matching without AI

**Infrastructure**
- Docker and Docker Compose
- GitHub Actions
- Environment-based configuration
- Structured logging

**Testing**
- pytest
- pytest-asyncio
- Testcontainers for PostgreSQL integration
- Angular unit tests
- Playwright Test for frontend end-to-end testing
- Python Playwright extraction tests
- Ruff, mypy and ESLint
- Security and dependency checks

Pin and lock compatible dependency versions. Do not automatically upgrade dependencies without reviewing compatibility.

## 3. Non-Negotiable Engineering Rules

### 3.1 Generic architecture

The system must not contain hardcoded company names, company-specific domain names, location lists, skill lists, role titles or customer-specific business rules.

Generic career-platform adapters are allowed because they represent reusable integration contracts, not individual companies.

When a source requires special handling, prefer a configurable extraction strategy or reusable adapter.

Clearly report unsupported websites.

Never claim the system can extract jobs from every website.

### 3.2 Modular design

Use a modular monolith with well-defined responsibilities:

- Identity and Authentication
- Users and Profiles
- Roles and Permissions
- Preferences
- Companies
- Career Discovery
- Job Extraction
- Job Normalization
- Job Matching
- AI Provider Integration
- Scan Orchestration
- Audit and Observability

Keep business logic independent from frameworks and external integrations wherever practical.

Do not introduce microservices or excessive abstractions without demonstrating a real need.

### 3.3 Security

Implement:

- Secure password hashing using Argon2id.
- JWT access tokens.
- Refresh-token rotation and revocation.
- Secure browser session handling.
- Database-driven RBAC.
- Authorization on backend operations.
- Validation of user-controlled URLs.
- SSRF protection, including redirect and DNS validation.
- Protection against internal/private-network requests.
- Rate limits and safe resource usage.
- Protection against prompt injection from scraped content.
- Secret management through environment variables.

Do not bypass CAPTCHA, login restrictions, or website access controls.

### 3.4 Code quality

- Use strict typing.
- Follow SOLID principles pragmatically.
- Avoid unnecessary duplication.
- Use dependency injection where useful.
- Handle errors predictably.
- Add meaningful logging.
- Keep functions and modules focused.
- Avoid speculative functionality.
- Prefer readable code over clever abstractions.

### 3.5 Documentation

Every phase must explain:

- What was implemented.
- Why the chosen design was used.
- Alternatives considered.
- Files created or modified.
- Important business logic.
- API contracts.
- Database changes.
- Security considerations.
- Tests performed.
- Known limitations.
- Pending functionality.

Documentation is part of completion, not optional follow-up work.

## 4. Architecture

Use the following logical flow:

Angular Application
→ FastAPI Backend
→ PostgreSQL

For asynchronous discovery:

FastAPI
→ Queue
→ Background Worker
→ Career Source Discovery
→ Job Extraction
→ Normalization
→ PostgreSQL

For matching:

Normalized Job
→ Preference Filters
→ Deterministic Matching
→ Optional AI Enrichment
→ Explainable Match Result

Use PostgreSQL as the authoritative source of data.

Queue messages and background workers must support retries, idempotency, error handling and safe recovery.

## 5. Suggested Repository Structure

```text
career-intelligence/
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── core/
│   │   │   ├── api/
│   │   │   ├── db/
│   │   │   ├── modules/
│   │   │   │   ├── identity/
│   │   │   │   ├── users/
│   │   │   │   ├── preferences/
│   │   │   │   ├── companies/
│   │   │   │   ├── discovery/
│   │   │   │   ├── extraction/
│   │   │   │   ├── jobs/
│   │   │   │   └── matching/
│   │   │   ├── integrations/
│   │   │   └── workers/
│   │   ├── migrations/
│   │   └── tests/
│   └── web/
│       ├── src/
│       └── e2e/
├── infrastructure/
├── docs/
│   ├── architecture/
│   ├── decisions/
│   ├── phases/
│   ├── testing/
│   └── operations/
├── .github/workflows/
├── compose.yaml
├── compose.test.yaml
├── .env.example
└── README.md
```

Create modules as they become necessary. Do not create large collections of empty placeholder files.

## 6. Phase-by-Phase Implementation

### Phase 0 — Project Foundation

**Objective:** Establish the working development environment and engineering standards.

Implement:

- Repository structure.
- FastAPI application skeleton.
- Angular application skeleton.
- PostgreSQL database connection.
- SQLAlchemy configuration.
- Alembic migrations.
- Environment-based settings.
- Health and readiness endpoints.
- Docker Compose.
- Structured logging.
- Global exception handling.
- pytest setup.
- PostgreSQL integration-test setup.
- Playwright frontend test setup.
- GitHub Actions CI.
- Initial documentation.

Expected endpoints:

- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`

Required tests:

- Docker builds and starts.
- FastAPI health checks respond correctly.
- PostgreSQL connectivity works.
- Database-unavailable conditions are handled.
- Alembic migrations succeed.
- Angular loads.
- Angular communicates with FastAPI.
- Playwright smoke tests pass.
- Linting and type checks pass.
- CI passes.

**Deliverable:** A runnable engineering foundation without job-search business functionality.

Stop and request approval before Phase 1.

### Phase 1 — Authentication, User Profiles and RBAC

Implement:

- Public registration.
- Login and logout.
- Password hashing.
- JWT authentication.
- Refresh-token rotation.
- Session revocation.
- Current-user endpoint.
- User profile management.
- Database-driven roles and permissions.
- Backend permission dependencies.
- Angular route guards.
- Secure frontend session handling.
- Registration and login screens.

Design roles and permissions to be extensible.

Do not hardcode authorization decisions throughout controllers.

Required tests:

- Registration validation.
- Duplicate registration.
- Correct and incorrect login.
- Password protection.
- Expired and invalid JWTs.
- Refresh-token rotation.
- Revoked sessions.
- Permission enforcement.
- Unauthorized API access.
- User data isolation.
- Playwright registration/login/logout workflows.

**Deliverable:** Secure multi-user application foundation.

Stop for approval.

### Phase 2 — Company and Preference Management

Implement:

- Company creation from name or website.
- Company identity and URL validation.
- Career URL management.
- User preference profiles.
- Preferred skills and keywords.
- Required skills.
- Excluded keywords.
- Job titles and seniority preferences.
- Locations and remote-work preferences.
- Experience requirements.
- Configurable matching weights.
- Angular company and preference-management interfaces.

Users must be able to create multiple preference profiles.

Store preference configuration in the database rather than hardcoding business values.

Required tests:

- Company input validation.
- Duplicate company handling.
- Preference CRUD.
- Invalid and conflicting preferences.
- Weight validation.
- User ownership and permissions.
- Playwright form and management workflows.

**Deliverable:** Configurable company and preference management.

Stop for approval.

### Phase 3 — Generic Career Discovery

Implement:

- Company domain resolution.
- Official website identification.
- Homepage career-link discovery.
- Sitemap inspection.
- Career-source identification.
- Recognition of supported ATS platforms.
- Scan request management.
- Asynchronous scan processing.
- Redis and Celery integration.
- Scan lifecycle and status tracking.
- Error handling and retry policies.
- Domain-level rate limiting.
- Secure outgoing HTTP requests.

A company name must not automatically resolve to an arbitrary similarly named business.

If confidence is insufficient, return candidate domains for user selection.

Required tests:

- Company-name resolution.
- Website validation.
- Career-link discovery.
- Redirect handling.
- Invalid domains.
- Timeouts.
- SSRF and private IP blocking.
- Scan queue processing.
- Retry handling.
- Scan status persistence.
- Playwright scan initiation and status display.

**Deliverable:** A reliable engine that discovers career sources and records scan results.

Stop for approval.

### Phase 4 — Job Extraction and Normalization

Implement reusable extraction strategies in this order:

1. Official public job-listing APIs.
2. Structured job-posting data.
3. Generic HTML extraction.
4. JavaScript browser extraction using Playwright.

Support reusable integrations for recognized ATS platforms when their public interfaces are available and permitted.

Implement:

- Job normalization.
- Source identifiers.
- Canonical job URLs.
- Pagination handling.
- Duplicate detection.
- Job description extraction.
- Job metadata extraction.
- Scan-to-job associations.
- Extraction confidence.
- Source failure reporting.
- Job-listing and detail APIs.
- Angular job explorer.

Use a normalized model containing title, company, location, work mode, description, requirements, employment type, source URL, dates and extraction metadata.

Do not fabricate missing values.

Required tests:

- API-based extraction.
- Static HTML extraction.
- Browser-rendered extraction.
- Pagination.
- Malformed content.
- Duplicate jobs.
- Missing information.
- Incorrect source results.
- Inaccessible pages.
- Source fixture regression tests.
- Playwright job-listing workflows.

**Deliverable:** Jobs collected and displayed from supported career sources.

Stop for approval.

### Phase 5 — Matching Engine and AI Integration

Implement deterministic matching first.

Suggested configurable factors:

- Skills.
- Role/title.
- Location and work mode.
- Experience.
- Employment preferences.

Implement:

- Hard exclusion filters.
- Weighted scoring.
- Skill normalization.
- Required versus preferred criteria.
- Missing-information handling.
- Match explanations.
- Scoring algorithm versioning.
- Match persistence.
- Score recalculation after preference updates.
- Sorting and filtering by score.

Then implement optional AI enrichment through an `AIProvider` interface.

Start with OpenRouter.

AI must be configurable and replaceable without changing business-domain services.

Implement strict response validation, timeout handling, usage tracking and deterministic fallback.

Do not interpret the match percentage as a hiring probability.

Required tests:

- Exact-match scenarios.
- Partial-match scenarios.
- Required-skill failures.
- Location exclusions.
- Missing job information.
- Weight changes.
- Scoring boundaries.
- Deterministic reproducibility.
- AI provider mocks.
- Invalid AI output.
- AI provider unavailability.
- Playwright matching and explanation workflows.

**Deliverable:** Explainable job matching with optional AI enhancement.

Stop for approval.

### Phase 6 — MVP User Experience and Operational Completion

Implement:

- Unified dashboard.
- Company search history.
- Scan history.
- Matched-job explorer.
- Job filters.
- Saved jobs.
- Empty and failed-scan states.
- Clear confidence indicators.
- Pagination.
- Loading states.
- Responsive design.
- Accessibility improvements.
- Operational observability.

Repeated scans must avoid unnecessary duplication.

Do not add recurring notifications or automated applications without separate approval.

Required tests:

- Full discovery-to-matching journey.
- Multiple user isolation.
- Saved jobs.
- Filtering.
- Empty results.
- Error recovery.
- Responsive UI.
- Accessibility.
- Playwright complete user journeys.

**Deliverable:** Complete initial user-facing MVP.

Stop for approval.

### Phase 7 — Release Hardening and Final Documentation

Implement and verify:

- Full regression suite.
- Load testing.
- Security validation.
- Container security.
- Database migration safety.
- Backup and restore procedures.
- Dependency audits.
- Production configuration.
- Observability.
- Deployment instructions.
- Release documentation.
- Known limitations.
- Pending features register.

Perform fresh-environment installation tests.

**Deliverable:** Release candidate with verifiable technical documentation and test evidence.

Do not claim production readiness until the required checks pass.

## 7. Mandatory Workflow for Every Phase

Follow these steps strictly.

**Step 1 — Inspect**

Review the existing repository before suggesting modifications.

Do not overwrite working code unnecessarily.

**Step 2 — Plan**

Create a detailed plan containing:

- Goals.
- Scope.
- Files to create.
- Files to modify.
- Database changes.
- API contracts.
- Frontend components.
- Important technical decisions.
- Security risks.
- Testing strategy.
- Acceptance criteria.

**Step 3 — Approval**

Present the plan and STOP.

Do not implement until I explicitly approve that phase.

**Step 4 — Implementation**

After approval, implement the smallest logical set of changes.

Use incremental commits with meaningful commit messages where Git is configured.

**Step 5 — Testing**

Run all applicable:

- Unit tests.
- Integration tests.
- Playwright tests.
- Regression tests.
- Static checks.
- Security checks.

Fix problems before considering a task complete.

Do not falsely report unexecuted tests as passed.

**Step 6 — Documentation**

Update the phase documentation and architecture decision records.

Explain why key decisions were made.

**Step 7 — Completion Report**

Report:

- Implemented features.
- Files changed.
- Tests executed.
- Passed and failed results.
- Outstanding issues.
- Design decisions.
- Pending work.
- Next-phase dependencies.

**Step 8 — Stop**

Wait for my explicit approval before planning implementation of the next phase.

Never automatically begin the next phase.

## 8. Definition of Done

A phase is complete only when:

- Its acceptance criteria are met.
- Required functionality works.
- Required backend tests pass.
- Applicable Playwright tests pass.
- Existing regression tests pass.
- Authorization and security checks pass.
- Migrations are tested when applicable.
- CI succeeds, where configured.
- Documentation is updated.
- Test evidence is reported.
- No blocking defects remain.

If the execution environment lacks Docker, browser dependencies, network access or other required capabilities, mark the affected tests as **NOT VERIFIED**.

Do not silently skip testing.

## 9. Final Instructions to Codex

Act as a senior software architect, Python/FastAPI engineer, Angular engineer, security reviewer and QA engineer.

Prioritize correctness, maintainability, extensibility and transparent reporting.

Challenge architectural decisions that introduce unnecessary complexity.

Do not introduce features outside the approved scope.

Do not hardcode company-specific behavior.

Use AI selectively rather than making the entire product dependent on LLM responses.

Maintain updated documentation continuously.

Never move to another phase without explicit approval.

**IMPORTANT: Start by inspecting the repository, then present the detailed Phase 0 implementation plan. Do not write or modify code until I approve that plan.**

If Phase 0 is already implemented, audit it against the Phase 0 acceptance criteria instead of rebuilding it.
