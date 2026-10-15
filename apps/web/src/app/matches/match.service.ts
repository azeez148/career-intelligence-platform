import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { AuthService } from '../auth/auth.service';
import { AIAssessmentResponse, AIStatus, Match, MatchFilters, MatchPage, MatchRun, MatchStatusView } from './match-model';

@Injectable({ providedIn: 'root' })
export class MatchService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);

  list(profileId: string, filters: MatchFilters, offset = 0, limit = 20): Promise<MatchPage> {
    let params = new HttpParams().set('offset', offset).set('limit', limit);
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && value !== '') params = params.set(key, String(value));
    }
    return firstValueFrom(this.http.get<MatchPage>(`/api/v1/preferences/${profileId}/matches`, { params }));
  }
  get(profileId: string, jobId: string): Promise<Match> {
    return firstValueFrom(this.http.get<Match>(`/api/v1/preferences/${profileId}/matches/${jobId}`));
  }
  status(profileId: string): Promise<MatchStatusView> {
    return firstValueFrom(this.http.get<MatchStatusView>(`/api/v1/preferences/${profileId}/match-status`));
  }
  async recalculate(profileId: string): Promise<MatchRun> {
    await this.auth.bootstrap();
    return firstValueFrom(this.http.post<MatchRun>(`/api/v1/preferences/${profileId}/matches/recalculate`, {}));
  }
  aiStatus(): Promise<AIStatus> {
    return firstValueFrom(this.http.get<AIStatus>('/api/v1/ai/status'));
  }
  async assess(profileId: string, jobId: string): Promise<AIAssessmentResponse> {
    await this.auth.bootstrap();
    return firstValueFrom(this.http.post<AIAssessmentResponse>(
      `/api/v1/preferences/${profileId}/matches/${jobId}/ai-assessment`, {}));
  }
}
