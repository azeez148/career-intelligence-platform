import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { AuthService } from '../auth/auth.service';
import { JobDetail } from './job-detail';
import { JobList } from './job-list';
import { ExtractionRun, Job, runText } from './job-model';
import { JobService } from './job.service';

export function job(values: Partial<Job> = {}): Job {
  return {
    id: '00000000-0000-0000-0000-0000000000aa', company_id: 'company', company_name: 'Acme', source_id: 'source',
    title: 'Backend Engineer', canonical_url: 'https://boards.greenhouse.io/acme/jobs/1', location_text: null,
    work_mode: 'unknown', employment_type: 'unknown', department: null, posted_at: null,
    first_seen_at: '2026-10-01T00:00:00Z', last_seen_at: '2026-10-02T00:00:00Z', closed_at: null,
    extraction_method: 'ats_api', confidence: 'high', duplicate_of_job_id: null, source_job_id: '1',
    description_text: null, requirements_text: null, valid_through: null, field_sources: {}, observations: [],
    ...values,
  };
}

export function run(values: Partial<ExtractionRun> = {}): ExtractionRun {
  return {
    id: 'run', company_id: 'company', source_id: 'source', scan_id: 'scan', trigger: 'discovery', stage: 'static',
    status: 'succeeded', strategy: 'ats_api', confidence: 'high', jobs_found: 2, jobs_created: 2, jobs_updated: 0,
    jobs_unchanged: 0, jobs_closed: 0, complete: true, attempt_count: 1, failure_code: null,
    created_at: '', updated_at: '', started_at: null, completed_at: null, ...values,
  };
}

describe('job model', () => {
  it('describes run outcomes without inventing detail', () => {
    expect(runText(run())).toBe('Found 2 jobs.');
    expect(runText(run({ jobs_found: 1 }))).toBe('Found 1 job.');
    expect(runText(run({ status: 'partial', jobs_found: 40 }))).toContain('larger than the scan limits');
    expect(runText(run({ status: 'queued', stage: 'browser' }))).toBe('Waiting for a browser worker.');
    expect(runText(run({ status: 'unsupported', failure_code: 'no_jobs_recognized' }))).toContain('No job listings');
    expect(runText(run({ status: 'failed', failure_code: 'something_new' }))).toBe('Extraction ended without job listings.');
  });
});

describe('job service', () => {
  const bootstrap = vi.fn().mockResolvedValue(undefined);
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideHttpClient(),
    provideHttpClientTesting(), { provide: AuthService, useValue: { bootstrap } }] }));

  it('sends only meaningful filters', async () => {
    const service = TestBed.inject(JobService); const http = TestBed.inject(HttpTestingController);
    const promise = service.list({ q: 'engineer', work_mode: 'remote', status: 'all', include_duplicates: false,
      company_id: undefined }, 20);
    const request = http.expectOne(value => value.url === '/api/v1/jobs');
    const params = request.request.params;
    expect(params.keys().sort()).toEqual(['limit', 'offset', 'q', 'status', 'work_mode']);
    expect(params.get('q')).toBe('engineer'); expect(params.get('offset')).toBe('20');
    request.flush({ items: [], next_offset: null }); await promise;
  });

  it('bootstraps CSRF before requesting a manual extraction', async () => {
    const service = TestBed.inject(JobService); const http = TestBed.inject(HttpTestingController);
    const promise = service.extract('source-id'); await Promise.resolve();
    const request = http.expectOne('/api/v1/sources/source-id/extractions');
    expect(request.request.method).toBe('POST'); request.flush(run({ status: 'queued' }));
    expect((await promise).status).toBe('queued'); expect(bootstrap).toHaveBeenCalled();
  });
});

describe('job pages', () => {
  const list = vi.fn(); const get = vi.fn();
  function setup(query: Record<string, string> = {}, id = job().id): void {
    TestBed.configureTestingModule({ providers: [provideRouter([]),
      { provide: JobService, useValue: { list, get } },
      { provide: ActivatedRoute, useValue: {
        snapshot: { queryParamMap: convertToParamMap(query) }, paramMap: of(convertToParamMap({ id })) } },
    ] });
  }
  beforeEach(() => { list.mockReset(); get.mockReset(); });
  afterEach(() => TestBed.resetTestingModule());

  it('scopes the explorer to a source from the query string and appends pages', async () => {
    setup({ source_id: 'source-1' });
    list.mockResolvedValueOnce({ items: [job()], next_offset: 1 })
      .mockResolvedValueOnce({ items: [job({ id: 'second', title: 'Designer' })], next_offset: null });
    const fixture = TestBed.createComponent(JobList); fixture.detectChanges(); await fixture.whenStable();
    expect(list.mock.calls[0][0]).toMatchObject({ source_id: 'source-1', status: 'open' });
    await fixture.componentInstance.load(1); fixture.detectChanges();
    expect(fixture.componentInstance.items().map(row => row.title)).toEqual(['Backend Engineer', 'Designer']);
    expect(fixture.nativeElement.textContent).toContain('Location not stated');
    fixture.componentInstance.clearScope();
    expect(list.mock.calls[2][0].source_id).toBeUndefined();
  });

  it('renders descriptions as text and labels unknown values', async () => {
    setup();
    get.mockResolvedValue(job({ description_text: '<img src=x onerror=alert(1)> Build APIs\n- Python',
      field_sources: { title: 'heuristic', description_text: 'heuristic' }, confidence: 'low',
      extraction_method: 'static_html' }));
    const fixture = TestBed.createComponent(JobDetail); fixture.detectChanges(); await fixture.whenStable();
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('img')).toBeNull();
    expect(element.querySelector('.job-text')?.textContent).toContain('<img src=x onerror=alert(1)>');
    expect(element.textContent).toContain('Not stated');
    expect(element.textContent).toContain('No requirements section was identified');
    expect(element.textContent).toContain('Inferred from page layout: title, description.');
    const link = element.querySelector<HTMLAnchorElement>('a[target=_blank]');
    expect(link?.rel).toBe('noopener noreferrer nofollow');
  });
});
