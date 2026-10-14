import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from './auth.service';

export const authenticated: CanActivateFn = async (route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  try { await auth.load(); } catch { return router.createUrlTree(['/login'], { queryParams: { unavailable: '1' } }); }
  if (!auth.user()) return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
  const permission: unknown = route.data['permission'];
  return typeof permission !== 'string' || auth.user()?.permissions.includes(permission)
    ? true : router.createUrlTree(['/']);
};

export const guest: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  try { await auth.load(); } catch { return true; }
  return auth.user() ? router.createUrlTree(['/profile']) : true;
};
