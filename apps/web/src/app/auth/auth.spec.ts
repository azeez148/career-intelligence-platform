import { HttpClient, HttpXsrfTokenExtractor, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { AuthService, safeReturnUrl } from './auth.service';
import { authInterceptor } from './auth.interceptor';
import { Credentials } from './credentials';

describe('browser authentication', () => {
  let auth: AuthService;
  let http: HttpClient;
  let controller: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [
      provideHttpClient(withInterceptors([authInterceptor])), provideHttpClientTesting(), provideRouter([]),
    ] });
    auth = TestBed.inject(AuthService); http = TestBed.inject(HttpClient);
    controller = TestBed.inject(HttpTestingController);
  });
  afterEach(() => controller.verify());

  it('rejects external and unexpected return destinations', () => {
    for (const url of ['https://evil.example', '//evil.example', '/\\evil', '/login', '/profile/../login']) {
      expect(safeReturnUrl(url)).toBe('/profile');
    }
    expect(safeReturnUrl('/sessions')).toBe('/sessions');
    expect(safeReturnUrl('/companies/new')).toBe('/companies/new');
    expect(safeReturnUrl('/preferences/01234567-89ab-cdef-0123-456789abcdef/edit')).toContain('/preferences/');
    expect(safeReturnUrl('/scans/01234567-89ab-cdef-0123-456789abcdef')).toContain('/scans/');
    for (const path of ['/companies/../login', '/companies//evil', '/preferences/bad/edit', '/companies/%2f%2fevil']) {
      expect(safeReturnUrl(path)).toBe('/profile');
    }
  });

  it('never refreshes permission failures', async () => {
    const result = firstValueFrom(http.get('/api/v1/users/me'));
    controller.expectOne('/api/v1/users/me').flush({}, { status: 403, statusText: 'Forbidden' });
    await expect(result).rejects.toMatchObject({ status: 403 });
    controller.expectNone('/api/v1/auth/refresh');
  });

  it('coalesces concurrent refresh and retries each protected request once', async () => {
    const first = firstValueFrom(http.get('/api/v1/users/me'));
    const second = firstValueFrom(http.get('/api/v1/auth/sessions'));
    controller.expectOne('/api/v1/users/me').flush({}, { status: 401, statusText: 'Unauthorized' });
    controller.expectOne('/api/v1/auth/sessions').flush({}, { status: 401, statusText: 'Unauthorized' });
    await Promise.resolve();
    controller.expectOne('/api/v1/users/me').flush({}, { status: 401, statusText: 'Unauthorized' });
    await new Promise(resolve => setTimeout(resolve, 0));
    controller.expectOne('/api/v1/auth/csrf').flush(null);
    await new Promise(resolve => setTimeout(resolve, 0));
    controller.expectOne('/api/v1/auth/refresh').flush({ access_expires_at: 'later' });
    await new Promise(resolve => setTimeout(resolve, 0));
    controller.expectOne('/api/v1/users/me').flush({ id: 'user' });
    controller.expectOne('/api/v1/auth/sessions').flush({ items: [] });
    expect(await first).toEqual({ id: 'user' });
    expect(await second).toEqual({ items: [] });
  });

  it('does not rotate again after another tab refreshed', async () => {
    const result = auth.refresh();
    await Promise.resolve();
    controller.expectOne('/api/v1/users/me').flush({ id: 'user' });
    await result;
    controller.expectNone('/api/v1/auth/refresh');
  });

  it('returns a retried 401 without a refresh loop', async () => {
    const result = firstValueFrom(http.get('/api/v1/users/me'));
    controller.expectOne('/api/v1/users/me').flush({}, { status: 401, statusText: 'Unauthorized' });
    await Promise.resolve();
    controller.expectOne('/api/v1/users/me').flush({ id: 'user' });
    await new Promise(resolve => setTimeout(resolve, 0));
    controller.expectOne('/api/v1/users/me').flush({}, { status: 401, statusText: 'Unauthorized' });
    await expect(result).rejects.toMatchObject({ status: 401 });
    controller.expectNone('/api/v1/auth/refresh');
  });

  it.each(['/api/v1/users/me/profile', '/api/v1/companies/id', '/api/v1/preferences/id'])('uses rotated CSRF when retrying %s', async (path) => {
    const result = firstValueFrom(http.request(path.includes('/users/') ? 'PATCH' : 'PUT', path,
      { body: { name: 'Updated' }, headers: { 'X-XSRF-TOKEN': 'previous' } }));
    controller.expectOne(path).flush({}, { status: 401, statusText: 'Unauthorized' });
    await Promise.resolve();
    controller.expectOne('/api/v1/users/me').flush({}, { status: 401, statusText: 'Unauthorized' });
    await new Promise(resolve => setTimeout(resolve, 0));
    controller.expectOne('/api/v1/auth/csrf').flush(null);
    await new Promise(resolve => setTimeout(resolve, 0));
    vi.spyOn(TestBed.inject(HttpXsrfTokenExtractor), 'getToken').mockReturnValue('rotated');
    controller.expectOne('/api/v1/auth/refresh').flush({});
    await new Promise(resolve => setTimeout(resolve, 0));
    const retry = controller.expectOne(path);
    expect(retry.request.headers.get('X-XSRF-TOKEN')).toBe('rotated');
    retry.flush({});
    await result;
  });

  it('keeps tokens out of user state and browser storage', async () => {
    const result = auth.login('person@example.com', 'a long enough password');
    controller.expectOne('/api/v1/auth/csrf').flush(null);
    await new Promise(resolve => setTimeout(resolve, 0));
    const request = controller.expectOne('/api/v1/auth/login');
    const user = { id: 'id', email: 'person@example.com', display_name: 'Person', bio: '', permissions: [] };
    request.flush({ user, access_expires_at: 'later' });
    await result;
    expect(auth.user()).toEqual(user);
    expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0);
  });
});

describe('credentials form', () => {
  it('blocks invalid registration without making a request', async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({ imports: [Credentials], providers: [provideRouter([]),
      provideHttpClient(), provideHttpClientTesting(),
      { provide: ActivatedRoute, useValue: { snapshot: { data: { registration: true }, queryParamMap: new Map() } } },
    ] });
    const fixture = TestBed.createComponent(Credentials);
    fixture.componentInstance.form.setValue({ email: 'bad', password: 'short', display_name: '' });
    await fixture.componentInstance.submit();
    expect(fixture.componentInstance.form.invalid).toBe(true);
    TestBed.inject(HttpTestingController).expectNone('/api/v1/auth/register');
  });
});
