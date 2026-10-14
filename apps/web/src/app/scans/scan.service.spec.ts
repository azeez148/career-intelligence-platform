import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { AuthService } from '../auth/auth.service';
import { ScanService } from './scan.service';

describe('scan service', () => {
  const bootstrap = vi.fn().mockResolvedValue(undefined);
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideHttpClient(),
    provideHttpClientTesting(), { provide: AuthService, useValue: { bootstrap } }] }));

  it('bootstraps CSRF before starting a scan', async () => {
    const service = TestBed.inject(ScanService); const http = TestBed.inject(HttpTestingController);
    const promise = service.start('company-id'); await Promise.resolve();
    const request = http.expectOne('/api/v1/companies/company-id/scans');
    expect(request.request.method).toBe('POST'); request.flush({ id: 'scan-id' });
    expect((await promise).id).toBe('scan-id'); expect(bootstrap).toHaveBeenCalled();
  });

  it('sends bounded list filters as query parameters', async () => {
    const service = TestBed.inject(ScanService); const http = TestBed.inject(HttpTestingController);
    const promise = service.list(20, 'company-id', 'failed', 10);
    const request = http.expectOne(value => value.url === '/api/v1/scans');
    expect(request.request.params.get('offset')).toBe('20');
    expect(request.request.params.get('company_id')).toBe('company-id');
    expect(request.request.params.get('status')).toBe('failed');
    expect(request.request.params.get('limit')).toBe('10');
    request.flush({ items: [], next_offset: null }); await promise;
  });
});
