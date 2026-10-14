export type ScanStatus = 'queued' | 'running' | 'needs_input' | 'succeeded' |
  'unsupported' | 'failed' | 'superseded';

export interface DiscoveryCandidate {
  id: string; url: string; hostname: string; confidence: 'low' | 'medium' | 'high'; evidence: string[];
}

export interface CareerSource {
  id: string; url: string; kind: 'generic_page' | 'ats'; platform: string | null;
  discovery_method: string; evidence: string[]; created_at: string; updated_at: string;
}

export interface ScanSummary {
  id: string; company_id: string; parent_scan_id: string | null; status: ScanStatus;
  selected_url: string | null; failure_code: string | null; attempt_count: number;
  created_at: string; updated_at: string; started_at: string | null; completed_at: string | null;
}

export interface Scan extends ScanSummary {
  resolved_website_url: string | null; resolution_confidence: string | null;
  resolution_evidence: string[]; candidates: DiscoveryCandidate[]; sources: CareerSource[];
}

export interface ScanPage { items: ScanSummary[]; next_offset: number | null }
export interface ScanSelection { candidate_id?: string; website_url?: string }

const outcomes: Record<string, string> = {
  robots_disallowed: 'The site does not permit this discovery request.',
  no_career_source: 'No supported careers source was found.',
  unsupported_content: 'The selected URL did not return a supported web page.',
  http_status: 'The selected site did not return an accessible page.',
  dns_blocked: 'The selected hostname did not resolve to a permitted public address.',
  timeout: 'The selected site did not respond before the scan timed out.',
  response_too_large: 'The selected page exceeded the scan size limit.',
  scan_budget_exceeded: 'The scan reached its total download limit.',
  response_budget_exceeded: 'The scan reached its request limit.',
  internal_error: 'The scan could not be completed after bounded retries.',
  retry_exhausted: 'The selected site remained unavailable after bounded retries.',
};

export function outcomeText(scan: Scan): string {
  if (scan.status === 'queued') return 'Waiting for a discovery worker.';
  if (scan.status === 'running') return 'Inspecting public careers metadata.';
  if (scan.status === 'needs_input') return 'Choose a suggested website or enter the official website URL.';
  if (scan.status === 'succeeded') return 'Career source discovery completed.';
  if (scan.status === 'superseded') return 'A newer scan continues from this selection.';
  return outcomes[scan.failure_code ?? ''] ?? 'Discovery ended without a supported career source.';
}
