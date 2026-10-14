export type WorkMode = 'remote' | 'hybrid' | 'onsite' | 'unknown';
export type EmploymentType = 'full_time' | 'part_time' | 'contract' | 'temporary' | 'internship' | 'unknown';
export type Strategy = 'ats_api' | 'structured_data' | 'static_html' | 'browser';
export type Confidence = 'low' | 'medium' | 'high';
export type RunStatus = 'queued' | 'running' | 'succeeded' | 'partial' | 'unsupported' | 'failed';

export interface JobSummary {
  id: string; company_id: string; company_name: string | null; source_id: string; title: string;
  canonical_url: string; location_text: string | null; work_mode: WorkMode; employment_type: EmploymentType;
  department: string | null; posted_at: string | null; first_seen_at: string; last_seen_at: string;
  closed_at: string | null; extraction_method: Strategy; confidence: Confidence; duplicate_of_job_id: string | null;
}

export interface JobObservation { run_id: string; change: 'created' | 'updated' | 'unchanged'; observed_at: string }

export interface Job extends JobSummary {
  source_job_id: string | null; description_text: string | null; requirements_text: string | null;
  valid_through: string | null; field_sources: Record<string, string>; observations: JobObservation[];
}

export interface JobPage { items: JobSummary[]; next_offset: number | null }

export interface JobFilters {
  company_id?: string; source_id?: string; q?: string; work_mode?: WorkMode;
  employment_type?: EmploymentType; status?: 'open' | 'closed' | 'all'; include_duplicates?: boolean;
}

export interface ExtractionRun {
  id: string; company_id: string; source_id: string; scan_id: string | null; trigger: 'discovery' | 'manual';
  stage: 'static' | 'browser'; status: RunStatus; strategy: Strategy | null; confidence: Confidence | null;
  jobs_found: number; jobs_created: number; jobs_updated: number; jobs_unchanged: number; jobs_closed: number;
  complete: boolean; attempt_count: number; failure_code: string | null; created_at: string; updated_at: string;
  started_at: string | null; completed_at: string | null;
}

export const workModes: Record<WorkMode, string> = {
  remote: 'Remote', hybrid: 'Hybrid', onsite: 'On-site', unknown: 'Not stated',
};
export const employmentTypes: Record<EmploymentType, string> = {
  full_time: 'Full-time', part_time: 'Part-time', contract: 'Contract', temporary: 'Temporary',
  internship: 'Internship', unknown: 'Not stated',
};
export const strategies: Record<Strategy, string> = {
  ats_api: 'Official job board API', structured_data: 'Structured job data',
  static_html: 'Page listing (heuristic)', browser: 'Rendered page (browser)',
};
export const confidenceText: Record<Confidence, string> = {
  high: 'High confidence: published by the job board API.',
  medium: 'Medium confidence: from structured data embedded in the page.',
  low: 'Low confidence: inferred from page layout; verify on the source page.',
};

const runOutcomes: Record<string, string> = {
  robots_disallowed: 'The site does not permit automated access to this source.',
  source_not_found: 'The source no longer exists or the board identifier is wrong.',
  api_unavailable: 'The job board did not return an accessible listing.',
  malformed_content: 'The source returned content that could not be read safely.',
  no_jobs_recognized: 'No job listings could be recognized on this source.',
  http_status: 'The source did not return an accessible page.',
  render_failed: 'The rendered page could not be loaded.',
  render_timeout: 'The rendered page did not finish loading in time.',
  dns_blocked: 'The source hostname did not resolve to a permitted public address.',
  timeout: 'The source did not respond in time.',
  retry_exhausted: 'The source remained unavailable after bounded retries.',
  internal_error: 'Extraction could not be completed after bounded retries.',
};

export function runText(run: ExtractionRun): string {
  if (run.status === 'queued') return run.stage === 'browser' ? 'Waiting for a browser worker.' : 'Waiting for an extraction worker.';
  if (run.status === 'running') return run.stage === 'browser' ? 'Rendering the career page.' : 'Reading job listings.';
  if (run.status === 'succeeded') return `Found ${run.jobs_found} job${run.jobs_found === 1 ? '' : 's'}.`;
  if (run.status === 'partial') return `Found ${run.jobs_found} jobs; the listing was larger than the scan limits allow.`;
  return runOutcomes[run.failure_code ?? ''] ?? 'Extraction ended without job listings.';
}

export function isActive(run: ExtractionRun): boolean {
  return run.status === 'queued' || run.status === 'running';
}
