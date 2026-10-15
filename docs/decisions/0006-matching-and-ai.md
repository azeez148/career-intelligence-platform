# ADR 0006: deterministic, explainable matching with optional advisory AI

Status: accepted for Phase 5.

## Context

Users hold preference profiles with user-defined criteria and weights (ADR 0003). Phase 4 jobs carry structured title, location, work mode, and employment type, but skills and experience exist only in free text, and often not at all. Matching must be reproducible, explain itself, and never invent facts. AI is required to be optional and replaceable, and must never become the source of truth.

## Decision

**Pure scorer `deterministic-1`.** `modules/matching/scoring.py` has no I/O, clock, or randomness, and uses exact fractions with half-up rounding. Any rule change must bump the version, and persisted matches from older versions are rescored.

**Text matching without catalogs.** Phrases match as contiguous token sequences after NFKC normalization and case-folding. Separators between word characters are equivalent ("Node.js" ~ "node js"), meaningful symbols stay ("C++", "C#", ".NET"), and there are no plurals, stemming, or synonyms.

**Hard exclusions.** These exclude a job:
- an excluded keyword anywhere in the job text;
- a known work mode that conflicts with the remote policy;
- a required skill absent from the job's description or requirements.

When the job has no text to check, required skills are *unverified*, not failed (approved decision 1).

**Weighted factors with missing information left out** (approved decision 2). Each factor is computed only when the job can inform it. The score is out of the known weight, and coverage (known weight ÷ 100) is persisted, displayed, and used for ranking: matches under 50% coverage sort after fully informed matches. Experience reads only explicit "N years", "N+ years", and "N–M years" phrases.

**Persistence and recalculation.** `job_matches` stores the explanation document together with the algorithm version, criteria hash, and job content hash. Runs are triggered by saving a profile, by successful extraction runs, or manually. They flow through `matching_outbox` and the existing dispatcher and Celery pattern. Partial unique indexes allow at most one queued and one running run per profile, so bursts coalesce and a queued run waits while another is running. Workers rescore only stale rows and drop matches for closed jobs and cross-source duplicates.

**AI is advisory, on demand, and off by default** (approved decisions 3 and 4). The `AIProvider` protocol has OpenRouter and disabled implementations, and settings refuse to enable AI without a key and an operator-chosen model.
- Each request sends only the bounded job fields and that profile's criteria, with no account identifiers.
- The job text sits in one delimited block whose delimiter look-alikes are removed, and is declared untrusted. No tools are offered.
- Strict JSON-schema output is requested and then validated again locally.
- Every call is recorded in `ai_usage`, under a rolling 24-hour per-user cap. Only validated successes are cached, keyed by job content, criteria, model, and prompt version.
- AI output is never written to matches or jobs.

## Alternatives considered

- **Scoring unknown factors as 0.** Rejected: it penalizes sparse but legitimate postings and hides the reason.
- **Required skills as a soft penalty.** Rejected in favor of an explicit gate with an unverified state, which matches users' "must have" intent without punishing missing text.
- **Letting AI fill unknown factors.** Rejected for now: it makes scores model-dependent and non-reproducible.
- **Embedding or synonym matching.** Out of scope; it requires a catalog or a model, both excluded by ADR 0003.

## Consequences

- Literal phrase matching misses wording differences. Users list their own variants.
- Coverage-renormalized scores can be high on little evidence. The coverage display, the limited-information label, and the ranking order counter this.
- AI adds a third-party data flow and cost, but only when an operator enables it and a user explicitly asks.
