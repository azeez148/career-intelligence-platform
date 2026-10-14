import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Foundation } from './foundation';

describe('Foundation', () => {
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [Foundation], providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('shows loading then confirms the HTTP response contract', async () => {
    const fixture = TestBed.createComponent(Foundation);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Checking connection');
    expect(element.querySelector('button')?.disabled).toBe(true);
    http.expectOne('/api/v1/health/ready').flush({ status: 'ready', checks: { database: 'ok', schema: 'ok' } });
    await fixture.whenStable();
    expect(element.textContent).toContain('connected and ready');
  });

  it('shows an outage and recovers on retry', async () => {
    const fixture = TestBed.createComponent(Foundation);
    fixture.detectChanges();
    http.expectOne('/api/v1/health/ready').flush({}, { status: 503, statusText: 'Unavailable' });
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('temporarily unavailable');
    element.querySelector('button')?.click();
    http.expectOne('/api/v1/health/ready').flush({ status: 'ready', checks: { database: 'ok', schema: 'ok' } });
    await fixture.whenStable();
    expect(element.textContent).toContain('connected and ready');
  });

  it('handles network failure', async () => {
    const fixture = TestBed.createComponent(Foundation);
    http.expectOne('/api/v1/health/ready').error(new ProgressEvent('error'));
    await fixture.whenStable();
    expect(fixture.componentInstance.state()).toBe('unavailable');
  });
});
