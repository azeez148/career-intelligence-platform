import { JobSummary, WorkMode } from '../jobs/job-model';

export type MatchStatus = 'eligible' | 'excluded' | 'insufficient_information';
export type FactorStatus = 'matched' | 'partial' | 'not_matched' | 'unknown';

export interface MatchSummary {
  job: JobSummary; status: MatchStatus; score: number | null; coverage: number; limited: boolean;
  summary: string; computed_at: string;
}

export interface FactorExplanation {
  factor: string; weight: number; status: FactorStatus; score: string | null; contribution: string | null;
  matched: string[]; missing: string[]; found_in: Record<string, string>; text: string;
}

export interface Explanation {
  algorithm_version: string; status: MatchStatus; score: number | null; coverage: string; summary: string;
  flags: { code: string; text: string }[]; exclusions: { code: string; values: string[]; text: string }[];
  factors: FactorExplanation[];
}

export interface AIAssessment {
  model: string; created_at: string; result: { summary: string; requirements: string[]; notes: string[] };
}

export interface Match extends MatchSummary {
  algorithm_version: string; explanation: Explanation; ai_assessment: AIAssessment | null;
}

export interface MatchPage { items: MatchSummary[]; next_offset: number | null }

export interface MatchFilters {
  status?: MatchStatus | 'all'; min_score?: number; work_mode?: WorkMode; q?: string; sort?: 'score' | 'recent';
}

export interface MatchRun {
  id: string; trigger: 'preference_update' | 'jobs_changed' | 'manual';
  status: 'queued' | 'running' | 'succeeded' | 'partial' | 'failed';
  jobs_scored: number; jobs_unchanged: number; jobs_removed: number; failure_code: string | null;
  created_at: string; completed_at: string | null;
}

export interface MatchStatusView { latest_run: MatchRun | null; active: boolean; stale: boolean }
export interface AIStatus { enabled: boolean; daily_limit: number; remaining_today: number }
export interface AIAssessmentResponse {
  status: 'succeeded' | 'cached' | 'invalid_output' | 'unavailable' | 'timeout' | 'refused';
  message: string; assessment: AIAssessment | null; remaining_today: number;
}

export const DISCLAIMER = 'Match scores reflect how well a job fits your stated preferences, not your chance of being hired.';

export const factorLabels: Record<string, string> = {
  skills: 'Skills', title: 'Job title', location: 'Location', experience: 'Experience',
  employment: 'Employment type', keywords: 'Keywords',
};

export const factorStatusText: Record<FactorStatus, string> = {
  matched: 'Matched', partial: 'Partly matched', not_matched: 'Not matched', unknown: 'Not stated by the job',
};

export function coveragePercent(coverage: number | string): number {
  return Math.round(Number(coverage) * 100);
}

export function scoreText(match: MatchSummary): string {
  if (match.status === 'excluded') return 'Excluded';
  if (match.score === null) return 'Not enough information';
  return `${match.score}% match`;
}

export function runText(status: MatchStatusView): string {
  const run = status.latest_run;
  if (!run) return 'Matches have not been calculated yet.';
  if (run.status === 'queued' || run.status === 'running') return 'Updating matches…';
  if (run.status === 'failed') return 'Matches could not be updated after bounded retries.';
  if (run.status === 'partial') return 'Matches were updated for the first 5,000 jobs only.';
  return status.stale ? 'Some matches are out of date.' : 'Matches are up to date.';
}
