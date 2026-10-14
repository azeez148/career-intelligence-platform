import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { AuthService } from '../auth/auth.service';
import { Preference, PreferenceInput, PreferencePage } from './preference-model';

@Injectable({ providedIn: 'root' })
export class PreferenceService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  list(offset = 0): Promise<PreferencePage> { return firstValueFrom(this.http.get<PreferencePage>(`/api/v1/preferences?offset=${offset}`)); }
  get(id: string): Promise<Preference> { return firstValueFrom(this.http.get<Preference>(`/api/v1/preferences/${id}`)); }
  async save(data: PreferenceInput, id: string | null): Promise<Preference> {
    await this.auth.bootstrap();
    return firstValueFrom(id ? this.http.put<Preference>(`/api/v1/preferences/${id}`, data)
      : this.http.post<Preference>('/api/v1/preferences', data));
  }
  async remove(id: string): Promise<void> {
    await this.auth.bootstrap();
    await firstValueFrom(this.http.delete(`/api/v1/preferences/${id}`));
  }
}
