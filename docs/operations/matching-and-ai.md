# Matching and AI operations

## Runtime

The `worker` consumes the `discovery`, `extraction`, and `matching` queues, and the `dispatcher` publishes `matching_outbox` rows as `matching.run`. A run scores at most 5,000 open, non-duplicate jobs per profile; beyond that it reports `partial`. It retries up to 3 times, then ends `failed / retry_exhausted`. A queued run whose profile already has a running run waits 5 seconds and tries again.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `MATCHING_USER_HOUR_LIMIT` | 30 | Manual recalculations per user per hour. |
| `AI_ENABLED` | `false` | Enables advisory assessments. Requires `OPENROUTER_API_KEY` and `AI_MODEL`. |
| `AI_MODEL` | — | An OpenRouter model ID chosen by the operator. Pick one that supports structured outputs; requests set `provider.require_parameters` so OpenRouter only routes to endpoints that support them. |
| `OPENROUTER_API_KEY` | — | Secret; never logged or returned by the API. |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Must be the official URL in production. The test stack points it at a local stub. |
| `AI_TIMEOUT_SECONDS` | 20 | Per-request timeout, at most 60. |
| `AI_MAX_OUTPUT_TOKENS` | 800 | Sent as `max_completion_tokens`. |
| `AI_USER_DAILY_LIMIT` | 20 | Provider calls per user in any rolling 24 hours. Cached results don't count. |

To enable AI, set `AI_ENABLED=true`, `AI_MODEL`, and `OPENROUTER_API_KEY` in `.env`, then recreate the `api` container (and restart `web`, because Nginx resolves `api` once). `GET /api/v1/ai/status` should then report `enabled: true` for users with `ai:use:self`.

## Observe

- **Match runs:** `match_runs` holds trigger, status, scored, unchanged, and removed counts. `GET /api/v1/preferences/{id}/match-status` reports `active` and `stale`. Stale means matches exist from an older algorithm, criteria, or job content, or that open jobs are unscored.
- **AI usage:** query `ai_usage` per user and status. Token counts and cost come from the provider when it returns them. Statuses are `succeeded`, `invalid_output`, `unavailable`, `timeout`, and `refused`.
- **AI is advisory only.** Disabling it, or provider outages, change nothing in `job_matches`.

## Real-provider smoke test (manual, optional)

Automated tests never call OpenRouter. To smoke-test a real key:
1. Enable AI in a disposable stack.
2. Open any match and select **Ask AI**.
3. Confirm one `ai_usage` row with status `succeeded` and a cached `ai_assessments` row, and that the match score is unchanged.

Record the model and the result. This step stays **NOT VERIFIED** unless an operator runs it.
