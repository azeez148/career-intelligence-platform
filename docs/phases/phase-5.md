# Phase 5: matching engine and AI integration

Status: implemented and locally verified on 2026-10-15. Hosted CI runs after push. Phase 6 has not started.

## What was implemented

- **Deterministic matching** (`deterministic-1`):
  - catalog-free phrase matching;
  - hard exclusions: excluded keywords, remote policy, and required skills (unverified when the job has no text);
  - six weighted factors, with unknown factors left out and coverage reported;
  - exact half-up rounding and template explanations.

  It is pure and versioned, and reproducibility is pinned by a 60-case golden file.
- **Persistence and recalculation:**
  - `job_matches` with versioned inputs;
  - durable match runs, triggered by profile saves, successful extraction runs, and manual requests;
  - coalescing (one queued and one running run per profile), stale detection, and cleanup of closed and duplicate jobs.
- **API:**
  - `GET /api/v1/preferences/{id}/matches` with status, score, coverage, company, work-mode, text, and sort filters;
  - `GET …/matches/{job_id}`, `GET …/match-status`, and `POST …/matches/recalculate`;
  - `POST …/matches/{job_id}/ai-assessment` and `GET /api/v1/ai/status`.
- **AI:**
  - a provider-independent `AIProvider` interface with OpenRouter and disabled implementations;
  - strict schema output, injection-hardened prompts, timeouts, response caps, usage tracking, a daily cap, caching, and deterministic fallback;
  - off by default.
- **Angular:**
  - "View matches" on each profile;
  - ranked, excluded, and not-enough-information tabs with filters and polling recalculation status;
  - match detail with per-factor weights, results, and points;
  - the advisory AI panel with disclosure;
  - a "not a hiring probability" note wherever scores appear.
- **Migration `0006_matching`:** permissions `matches:read:self`, `matches:update:self`, and `ai:use:self` for members.

Design rationale is in [ADR 0006](../decisions/0006-matching-and-ai.md), operations in [matching and AI operations](../operations/matching-and-ai.md), and evidence in [Phase 5 verification](../testing/phase-5.md). The approved plan is in [phase-5-plan.md](phase-5-plan.md).

## Deviations from the plan and additions

- **Location with listed places.** When locations are listed but the job has no location text, the location factor is *unknown* even for remote roles, because geographic restrictions can't be checked.
- **Coalescing** uses two partial unique indexes, one queued and one running per profile, instead of one active index, so changes during a running run are not lost.
- **Extraction triggers rescoring after every successful or partial run**, not only when content changed. Stale detection makes unchanged rescoring a no-op.
- **The AI daily cap is a rolling 24 hours** and counts every provider call, including failures. Cache hits are free.
- **Fixed during this phase:** private responses for `/jobs`, `/sources`, `/extractions`, and `/ai` are now `Cache-Control: no-store`. The Phase 4 routes had been missed.
- **The AI stub** for browser journeys is served by the existing fixture-site container under the `ai-stub` alias. No new image was added.

## Known limitations

- Literal phrase matching: users list their own variants.
- Experience is read only from explicit year phrases.
- Scores of low-confidence (heuristic) jobs inherit their noisy text.
- A real OpenRouter smoke test is **NOT VERIFIED**; it is documented as an optional manual operator step.
- The limitations from earlier phases (browser image findings, the Nginx single-resolution behaviour, per-owner job copies) remain.

## Next-phase dependencies

Phase 6 (MVP UX):
- builds the dashboard, saved jobs, and unified history on `job_matches`, `match_runs`, and the explanation documents;
- must keep the hiring-probability disclaimer;
- should reuse coverage and confidence indicators;
- must keep AI optional.
