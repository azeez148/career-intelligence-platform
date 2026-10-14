import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, Router, RouterStateSnapshot, UrlTree, provideRouter } from '@angular/router';
import { authenticated, guest } from './auth.guards';
import { AuthService, User } from './auth.service';

describe('account guards', () => {
  const user = signal<User | null>(null);
  beforeEach(() => {
    user.set(null);
    TestBed.configureTestingModule({ providers: [provideRouter([]),
      { provide: AuthService, useValue: { user, load: async () => undefined } },
    ] });
  });
  it('redirects anonymous users with an internal return URL', async () => {
    const result = await TestBed.runInInjectionContext(() => authenticated(
      { data: {} } as ActivatedRouteSnapshot, { url: '/sessions' } as RouterStateSnapshot));
    expect(TestBed.inject(Router).serializeUrl(result as UrlTree)).toBe('/login?returnUrl=%2Fsessions');
  });
  it('permits granted permissions and rejects missing permissions', async () => {
    user.set({ id: 'id', email: 'user@example.com', display_name: 'User', bio: '', permissions: ['profile:read:self'] });
    const check = (permission: string) => TestBed.runInInjectionContext(() => authenticated(
      Object.assign(new ActivatedRouteSnapshot(), { data: { permission } }), { url: '/profile' } as RouterStateSnapshot));
    expect(await check('profile:read:self')).toBe(true);
    expect(TestBed.inject(Router).serializeUrl(await check('sessions:read:self') as UrlTree)).toBe('/');
  });
  it('redirects authenticated users away from credential forms', async () => {
    user.set({ id: 'id', email: 'user@example.com', display_name: 'User', bio: '', permissions: [] });
    const result = await TestBed.runInInjectionContext(() => guest({} as ActivatedRouteSnapshot, {} as RouterStateSnapshot));
    expect(TestBed.inject(Router).serializeUrl(result as UrlTree)).toBe('/profile');
  });
});
