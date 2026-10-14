import { HttpErrorResponse } from '@angular/common/http';

const messages: Record<string, string> = {
  blank_value: 'Values cannot be blank.', source_url: 'Use an absolute HTTP(S) URL with a public DNS hostname and standard port, without credentials or fragments.',
  company_identity: 'Enter a company name, website URL, or careers URL.',
  duplicate_values: 'Remove duplicate list entries.', too_many_values: 'Use at most 200 list entries in total.',
  preference_conflict: 'Required and preferred skills must be distinct; excluded keywords must not conflict with desired criteria.',
  experience_range: 'Minimum experience cannot exceed maximum experience.',
  weight_total: 'Matching weights must total 100.', weight_without_criteria: 'Every positive weight needs criteria for that factor.',
  company_duplicate: 'This company is already saved.', preference_duplicate: 'This preference profile name is already used.',
};

export function resourceError(error: unknown): string {
  if (!(error instanceof HttpErrorResponse)) return 'The service is unavailable. Please try again.';
  if (error.status === 401) return 'Your session has expired. Please sign in again.';
  if (error.status === 403) return 'You do not have permission, or request verification failed. Reload and try again.';
  if (error.status === 404) return 'This record was not found or is no longer available.';
  const body = error.error as { error?: { code?: string; issues?: { code: string }[] } } | null;
  const code = body?.error?.code;
  if (code && messages[code]) return messages[code];
  const issue = body?.error?.issues?.find(item => messages[item.code]);
  if (issue) return messages[issue.code];
  if (error.status === 422) return 'Check field lengths, list entries, and numeric values, then try again.';
  return 'The service is unavailable. Your changes have not been confirmed; reload before retrying an uncertain save.';
}
