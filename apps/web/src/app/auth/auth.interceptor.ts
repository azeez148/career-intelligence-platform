import { HttpErrorResponse, HttpInterceptorFn, HttpXsrfTokenExtractor } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, from, switchMap, throwError } from 'rxjs';
import { AuthService } from './auth.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const auth = inject(AuthService);
  const xsrf = inject(HttpXsrfTokenExtractor);
  const path = request.url.split('?')[0];
  const protectedRequest = request.url.startsWith('/api/v1/users/') ||
    request.url.startsWith('/api/v1/auth/sessions') || request.url === '/api/v1/auth/logout-all' ||
    ['/api/v1/companies', '/api/v1/preferences'].some(prefix => path === prefix || path.startsWith(prefix + '/'));
  return next(request).pipe(catchError((error: unknown) => {
    if (!protectedRequest || !(error instanceof HttpErrorResponse) || error.status !== 401) {
      return throwError(() => error);
    }
    return from(auth.refresh()).pipe(switchMap(() => {
      // Refresh rotates the CSRF cookie too; a retried mutation needs its new value.
      const token = xsrf.getToken();
      const retry = token && !['GET', 'HEAD'].includes(request.method)
        ? request.clone({ setHeaders: { 'X-XSRF-TOKEN': token } }) : request;
      return next(retry);
    }));
  }));
};
