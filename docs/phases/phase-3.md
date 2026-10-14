# Phase 3: generic career discovery

Status: implemented and locally verified on 2026-10-14; hosted CI pending push. Phase 4 has not started.

Phase 3 adds owner-scoped scan APIs and screens, explicit name-only domain confirmation, safe homepage/link/sitemap inspection, initial Greenhouse/Lever/Workday recognition, PostgreSQL outbox delivery through Redis/Celery, bounded retries and hostname rate limiting, and hardened outbound networking.

The implementation ends at career-source identification. It does not extract vacancies, create job records, render JavaScript sites, run schedules, match preferences, call AI models, send notifications, or automate applications.

The approved design and acceptance criteria remain in [the implementation plan](phase-3-plan.md). Architecture rationale is in [ADR 0004](../decisions/0004-career-discovery.md), operating procedures are in [career discovery operations](../operations/career-discovery.md), and reproduced checks are in [Phase 3 verification](../testing/phase-3.md).
