import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { AuthService } from '../auth/auth.service';
import { run } from '../jobs/jobs.spec';
import { JobService } from '../jobs/job.service';
import { Scan } from './scan-model';
import { ScanDetail } from './scan-detail';
import { ScanService } from './scan.service';

function scan(status: Scan['status']): Scan {
  return {
    id: '00000000-0000-0000-0000-000000000001', company_id: 'company', parent_scan_id: null,
    status, selected_url: null, failure_code: null, attempt_count: 0, created_at: '', updated_at: '',
    started_at: null, completed_at: null, resolved_website_url: null, resolution_confidence: null,
    resolution_evidence: [], candidates: [], sources: [], extractions: [],
  };
}

const source = {
  id: 'source', url: 'https://boards.greenhouse.io/acme', kind: 'ats' as const, platform: 'greenhouse',
  discovery_method: 'homepage_link', evidence: [], created_at: '', updated_at: '',
};

describe('scan detail', () => {
  const get = vi.fn(); const select = vi.fn(); const extract = vi.fn();
  beforeEach(() => {
    vi.useFakeTimers(); get.mockReset(); select.mockReset(); extract.mockReset();
    TestBed.configureTestingModule({ imports: [ScanDetail], providers: [provideRouter([]),
      { provide: ScanService, useValue: { get, select } },
      { provide: JobService, useValue: { extract } },
      { provide: AuthService, useValue: { user: () => ({ permissions: ['extractions:create:self'] }) } },
      { provide: ActivatedRoute, useValue: { snapshot: { paramMap: { get: () => scan('queued').id } } } },
    ] });
  });
  afterEach(() => { TestBed.resetTestingModule(); vi.useRealTimers(); });

  it('polls while active and stops after a terminal result', async () => {
    get.mockResolvedValueOnce(scan('queued')).mockResolvedValueOnce(scan('succeeded'));
    const fixture = TestBed.createComponent(ScanDetail); const detail = fixture.componentInstance;
    await detail.load(); expect(get).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(3000); expect(get).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(3000); expect(get).toHaveBeenCalledTimes(2);
    fixture.destroy();
  });

  it('preserves a rejected manual URL for correction', async () => {
    select.mockRejectedValue(new HttpErrorResponse({ status: 422 }));
    const detail = TestBed.createComponent(ScanDetail).componentInstance;
    detail.scan.set(scan('needs_input')); detail.manualUrl = 'https://candidate.example.org/';
    await detail.useManualUrl();
    expect(detail.manualUrl).toBe('https://candidate.example.org/');
    expect(detail.error()).toContain('Check field'); expect(detail.saving()).toBe(false);
  });

  it('keeps polling while a source extraction is active, then stops', async () => {
    const active = { ...scan('succeeded'), sources: [source], extractions: [run({ status: 'running' })] };
    const done = { ...active, extractions: [run()] };
    get.mockResolvedValueOnce(active).mockResolvedValueOnce(done);
    const fixture = TestBed.createComponent(ScanDetail); const detail = fixture.componentInstance;
    await detail.load(); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Reading job listings.');
    await vi.advanceTimersByTimeAsync(3000); expect(get).toHaveBeenCalledTimes(2);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('View jobs from this source');
    await vi.advanceTimersByTimeAsync(3000); expect(get).toHaveBeenCalledTimes(2);
    fixture.destroy();
  });

  it('re-extracts one source and reports rate limits', async () => {
    const detail = TestBed.createComponent(ScanDetail).componentInstance;
    detail.scan.set({ ...scan('succeeded'), sources: [source], extractions: [run()] });
    extract.mockResolvedValueOnce(run({ id: 'manual', status: 'queued', trigger: 'manual' }));
    await detail.reExtract(source);
    expect(detail.runFor(source)?.id).toBe('manual'); expect(detail.isRunActive(source)).toBe(true);
    extract.mockRejectedValueOnce(new HttpErrorResponse({ status: 429, error: { error: { code: 'rate_limited' } } }));
    await detail.reExtract(source);
    expect(detail.error()).toContain('Too many requests'); expect(detail.extracting()).toBeNull();
  });
});
