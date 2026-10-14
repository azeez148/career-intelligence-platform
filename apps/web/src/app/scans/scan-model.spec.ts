import { Scan } from './scan-model';
import { outcomeText } from './scan-model';

function scan(status: Scan['status'], failure_code: string | null = null): Scan {
  return {
    id: 'scan', company_id: 'company', parent_scan_id: null, status, selected_url: null,
    failure_code, attempt_count: 0, created_at: '', updated_at: '', started_at: null,
    completed_at: null, resolved_website_url: null, resolution_confidence: null,
    resolution_evidence: [], candidates: [], sources: [], extractions: [],
  };
}

describe('scan outcome text', () => {
  it('maps lifecycle and safe failure codes without exposing remote details', () => {
    expect(outcomeText(scan('queued'))).toContain('Waiting');
    expect(outcomeText(scan('needs_input'))).toContain('Choose');
    expect(outcomeText(scan('unsupported', 'robots_disallowed'))).toContain('does not permit');
    expect(outcomeText(scan('failed', 'unknown-private-error'))).not.toContain('unknown-private-error');
  });
});
