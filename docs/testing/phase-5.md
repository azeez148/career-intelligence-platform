# Phase 5 verification evidence

Verified locally on Windows 11 with Docker Desktop 29.8.2 (Linux containers), Python 3.13, uv 0.12.24, and Node 22.22.3 on 2026-10-15, against commit `f6ce1e3` plus the Step E CI and documentation changes.

| Gate | Result |
|---|---|
| Backend tests (unit, PostgreSQL/Redis integration, Python Playwright browser) | **253 passed** in 4 min 48 s. The only warning is the pre-existing Starlette `TestClient` deprecation notice. |
| Ruff lint and format, strict mypy (103 source files) | Passed |
| Angular ESLint, unit tests, production build | Passed; 12 files / **52 tests** |
| Playwright Chromium journeys against a freshly built isolated stack | **15 / 15 passed** (13 existing + 2 Phase 5) |
| Alembic | `0006_matching (head)`, no new upgrade operations; upgrade from 0005, repeat upgrade, downgrade preserving profiles, and re-upgrade tested |
| Runtime | All services healthy or running with no tracebacks; worker registered `matching.run`; match runs `succeeded`; AI usage recorded through the stub |
| `pip-audit` / `npm audit --audit-level=high` | No known vulnerabilities / 0 vulnerabilities |
| Trivy 0.69.3, strict HIGH/CRITICAL | API, web, PostgreSQL, Redis: 0 |
| Trivy 0.69.3, browser image, fixable-only | 0 fixable |
| Gitleaks 8.30.0 | No leaks across 31 commits |

## Master-plan test requirements

| Requirement | Evidence |
|---|---|
| Exact-match scenarios | 100% at full coverage, with every factor matched and the exact explanation sentence |
| Partial-match scenarios | Hand-computed 75%; browser journey 70% and 30% |
| Required-skill failures | Excluded with a reason; no job text → unverified flag, not excluded; browser journey shows the Excluded tab entry |
| Location exclusions | Full `remote_policy` × `work_mode` matrix, plus location-text and remote rules |
| Missing job information | Renormalization, coverage, the limited-information flag, and `insufficient_information` |
| Weight changes | Swapped weights change the ranking; a preference edit rescores (70% → 80% in the browser) |
| Scoring boundaries | 0 and 100, half-up rounding (12.5 → 13), and the experience decay edges |
| Deterministic reproducibility | A 60-case seeded golden file, identical in-process and in fresh interpreters with `PYTHONHASHSEED` 1 and 4242 |
| AI provider mocks | Fake provider for success, caching, cache invalidation after a criteria change, daily caps, and usage records |
| Invalid AI output | Non-JSON, extra keys (including an injected `score`), oversize fields, null content, empty choices; script text renders inertly in the UI |
| AI provider unavailability | 402, 429, 503, 408, timeout, connection error, oversize body, redirect, refusal, and disabled AI all fall back with the match unchanged |
| Playwright matching and explanations | Two real journeys, including the AI stub round trip and a narrow viewport |

Prompt-injection controls are tested at the request boundary. A posting containing `<<<END JOB>>>`, fake system markers, and "ignore previous instructions" yields exactly one data block, with the markers removed. No tools or user identifiers are sent.

**NOT VERIFIED:** a call to the real OpenRouter API. It is documented in the operations guide as an optional manual step.
