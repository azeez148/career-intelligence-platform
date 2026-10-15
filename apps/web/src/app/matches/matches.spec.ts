import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { AuthService } from '../auth/auth.service';
import { job } from '../jobs/jobs.spec';
import { PreferenceService } from '../preferences/preference.service';
import { MatchDetail } from './match-detail';
import { MatchList } from './match-list';
import { DISCLAIMER, Match, MatchStatusView, MatchSummary, runText, scoreText } from './match-model';
import { MatchService } from './match.service';

const PROFILE = '00000000-0000-0000-0000-0000000000bb';

function summary(values: Partial<MatchSummary> = {}): MatchSummary {
  return { job: job(), status: 'eligible', score: 75, coverage: 1, limited: false, summary: 'Strongest match: skills.',
    computed_at: '2026-10-15T00:00:00Z', ...values };
}

function match(values: Partial<Match> = {}): Match {
  return {
    ...summary(), algorithm_version: 'deterministic-1', ai_assessment: null,
    explanation: {
      algorithm_version: 'deterministic-1', status: 'eligible', score: 75, coverage: '1.0000', summary: '',
      flags: [{ code: 'low_confidence_source', text: 'Job details were inferred from page layout and may be incomplete.' }],
      exclusions: [],
      factors: [{ factor: 'skills', weight: 50, status: 'partial', score: '0.5000', contribution: '25.00',
        matched: ['Python'], missing: ['<b>Go</b>'], found_in: { Python: 'description' },
        text: 'Found 1 of 2 skills in the description: Python. Not found: <b>Go</b>.' }],
    },
    ...values,
  };
}

function status(values: Partial<MatchStatusView> = {}): MatchStatusView {
  return { latest_run: { id: 'run', trigger: 'manual', status: 'succeeded', jobs_scored: 2, jobs_unchanged: 0,
    jobs_removed: 0, failure_code: null, created_at: '', completed_at: '' }, active: false, stale: false, ...values };
}

describe('match model', () => {
  it('never frames a score as a hiring probability and labels special states', () => {
    expect(DISCLAIMER).toContain('not your chance of being hired');
    expect(scoreText(summary())).toBe('75% match');
    expect(scoreText(summary({ status: 'excluded', score: 0 }))).toBe('Excluded');
    expect(scoreText(summary({ status: 'insufficient_information', score: null }))).toBe('Not enough information');
    expect(runText(status())).toBe('Matches are up to date.');
    expect(runText(status({ stale: true }))).toBe('Some matches are out of date.');
    expect(runText(status({ latest_run: null }))).toBe('Matches have not been calculated yet.');
  });
});

describe('match service', () => {
  const bootstrap = vi.fn().mockResolvedValue(undefined);
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(),
    { provide: AuthService, useValue: { bootstrap } }] }));

  it('sends filters and bootstraps CSRF before AI and recalculation requests', async () => {
    const service = TestBed.inject(MatchService); const http = TestBed.inject(HttpTestingController);
    const listed = service.list(PROFILE, { status: 'eligible', min_score: 40, q: undefined });
    const request = http.expectOne(value => value.url === `/api/v1/preferences/${PROFILE}/matches`);
    expect(request.request.params.get('min_score')).toBe('40'); expect(request.request.params.has('q')).toBe(false);
    request.flush({ items: [], next_offset: null }); await listed;
    const assessed = service.assess(PROFILE, 'job'); await Promise.resolve();
    const post = http.expectOne(`/api/v1/preferences/${PROFILE}/matches/job/ai-assessment`);
    expect(post.request.method).toBe('POST'); post.flush({ status: 'unavailable' });
    expect((await assessed).status).toBe('unavailable'); expect(bootstrap).toHaveBeenCalled();
  });
});

describe('match pages', () => {
  const api = { list: vi.fn(), get: vi.fn(), status: vi.fn(), recalculate: vi.fn(), aiStatus: vi.fn(), assess: vi.fn() };
  let permissions: string[] = [];
  beforeEach(() => {
    vi.useFakeTimers(); Object.values(api).forEach(fn => fn.mockReset()); permissions = ['matches:update:self'];
    TestBed.configureTestingModule({ providers: [provideRouter([]),
      { provide: MatchService, useValue: api },
      { provide: PreferenceService, useValue: { get: vi.fn().mockResolvedValue({ name: 'Engineering' }) } },
      { provide: AuthService, useValue: { user: () => ({ permissions }) } },
      { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ id: PROFILE, jobId: job().id }) } } },
    ] });
  });
  afterEach(() => { TestBed.resetTestingModule(); vi.useRealTimers(); });

  it('switches tabs, polls only while a run is active, and reloads when it finishes', async () => {
    api.list.mockResolvedValue({ items: [summary()], next_offset: null });
    api.status.mockResolvedValueOnce(status({ active: true })).mockResolvedValueOnce(status());
    const fixture = TestBed.createComponent(MatchList); fixture.detectChanges(); await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain(DISCLAIMER);
    expect(fixture.nativeElement.textContent).toContain('75% match');
    await vi.advanceTimersByTimeAsync(3000);
    expect(api.status).toHaveBeenCalledTimes(2); expect(api.list).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(6000); expect(api.status).toHaveBeenCalledTimes(2);
    fixture.componentInstance.selectTab('excluded');
    expect(api.list.mock.calls.at(-1)?.[1]).toMatchObject({ status: 'excluded', min_score: undefined });
    fixture.destroy();
  });

  it('renders explanations as text and hides AI when it is disabled', async () => {
    permissions = ['ai:use:self'];
    api.get.mockResolvedValue(match()); api.aiStatus.mockResolvedValue({ enabled: false, daily_limit: 20, remaining_today: 0 });
    const fixture = TestBed.createComponent(MatchDetail); fixture.detectChanges(); await fixture.whenStable();
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('b')).toBeNull();
    expect(element.textContent).toContain('Not found: <b>Go</b>.');
    expect(element.textContent).toContain('Job details were inferred from page layout');
    expect(element.textContent).not.toContain('Ask AI');
  });

  it('asks AI once, shows advisory output, and reports fallbacks', async () => {
    permissions = ['ai:use:self'];
    api.get.mockResolvedValue(match()); api.aiStatus.mockResolvedValue({ enabled: true, daily_limit: 20, remaining_today: 3 });
    const fixture = TestBed.createComponent(MatchDetail); fixture.detectChanges(); await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('cannot change the score');
    api.assess.mockResolvedValueOnce({ status: 'timeout', message: 'The AI service did not respond in time. Your match is unchanged.',
      assessment: null, remaining_today: 2 });
    await fixture.componentInstance.askAI(); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Your match is unchanged.');
    expect(fixture.componentInstance.aiStatus()?.remaining_today).toBe(2);
    api.assess.mockResolvedValueOnce({ status: 'succeeded', message: '', remaining_today: 1, assessment: {
      model: 'vendor/model', created_at: '2026-10-15T00:00:00Z',
      result: { summary: '<script>x</script> Python roles', requirements: ['Python'], notes: ['Seniority not stated'] } } });
    await fixture.componentInstance.askAI(); fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('script')).toBeNull();
    expect(element.textContent).toContain('<script>x</script> Python roles');
    expect(element.textContent).toContain('Seniority not stated');
    expect(element.textContent).toContain('75% match');
  });
});
