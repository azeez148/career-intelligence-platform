# Phase 5 local checklist

1. **Start the stack.** Follow steps 1–4 of the [Phase 4 local checklist](phase-4-local-check.md) with project name `career-phase5-check`. The worker's task list must include `matching.run`. The test overlay enables AI against the local stub (`OPENROUTER_BASE_URL=http://ai-stub/api/v1`), so no real key is used.
2. **Extract jobs.** Register, add a company with website `http://jobs-fixture.com/`, and select **Discover careers**. Wait for "View jobs from this source" (3 jobs).
3. **Create a profile.** Open **Preferences** → **Add preference profile**:
   - name `Reliability`;
   - Preferred skills `Linux` and `SQL` (one per line);
   - Job titles `Site Reliability Engineer`;
   - Skills weight 60, Title and seniority weight 40.

   Save.
4. **Check the ranking.** Select **View matches**. Expect "Matches are up to date.", Site Reliability Engineer at 70%, Data Analyst at 30%, and the note that scores are not a chance of being hired.
5. **Check the explanation.** Open Site Reliability Engineer. Expect "Found 1 of 2 skills in the requirements: Linux. Not found: SQL." and a per-factor table.
6. **Ask AI.** Select **Ask AI**. Expect the stub summary about Linux and incident response, "Salary is not stated.", and an unchanged 70% score. Reloading shows the cached assessment.
7. **Check rescoring.** Edit the profile: Preferred skills `SQL`, Required skills `Linux`. Save, then view matches. Expect one ranked job at 80%, and Data Analyst under **Excluded** with "A required skill is not mentioned: Linux."
8. **Check AI disabled.** Run the stack without the test overlay's AI settings (or set `AI_ENABLED=false` for `api`). The AI panel disappears and `GET /api/v1/ai/status` reports `enabled: false`.
9. **Run the gates.** Run the backend and frontend gates from the Phase 4 checklist, then tear down with `docker compose -p career-phase5-check -f compose.yaml -f compose.test.yaml down --volumes`.
