import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { AuthService } from '../auth/auth.service';
import { ExtractionRun, Job, JobFilters, JobPage } from './job-model';

@Injectable({ providedIn: 'root' })
export class JobService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);

  list(filters: JobFilters, offset = 0, limit = 20): Promise<JobPage> {
    let params = new HttpParams().set('offset', offset).set('limit', limit);
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== '' && value !== false) params = params.set(key, String(value));
    }
    return firstValueFrom(this.http.get<JobPage>('/api/v1/jobs', { params }));
  }
  get(id: string): Promise<Job> {
    return firstValueFrom(this.http.get<Job>(`/api/v1/jobs/${id}`));
  }
  run(id: string): Promise<ExtractionRun> {
    return firstValueFrom(this.http.get<ExtractionRun>(`/api/v1/extractions/${id}`));
  }
  async extract(sourceId: string): Promise<ExtractionRun> {
    await this.auth.bootstrap();
    return firstValueFrom(this.http.post<ExtractionRun>(`/api/v1/sources/${sourceId}/extractions`, {}));
  }
}
