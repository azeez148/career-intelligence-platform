import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { timeout } from 'rxjs';

export interface Readiness {
  status: 'ready' | 'not_ready';
  checks: {
    database: 'ok' | 'unavailable';
    schema: 'ok' | 'mismatch' | 'unknown';
  };
}

@Injectable({ providedIn: 'root' })
export class HealthService {
  private readonly http = inject(HttpClient);
  readiness() {
    return this.http.get<Readiness>('/api/v1/health/ready').pipe(timeout(5000));
  }
}
