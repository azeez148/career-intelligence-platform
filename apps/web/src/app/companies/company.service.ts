import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { AuthService } from '../auth/auth.service';

export interface CompanyInput { name: string | null; website_url: string | null; careers_url: string | null }
export interface Company extends CompanyInput {
  id: string; display_label: string; source_status: 'unverified'; created_at: string; updated_at: string;
}
export interface CompanyPage { items: Company[]; next_offset: number | null }

@Injectable({ providedIn: 'root' })
export class CompanyService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  list(offset = 0): Promise<CompanyPage> { return firstValueFrom(this.http.get<CompanyPage>(`/api/v1/companies?offset=${offset}`)); }
  get(id: string): Promise<Company> { return firstValueFrom(this.http.get<Company>(`/api/v1/companies/${id}`)); }
  async save(data: CompanyInput, id: string | null): Promise<Company> {
    await this.auth.bootstrap();
    return firstValueFrom(id ? this.http.put<Company>(`/api/v1/companies/${id}`, data)
      : this.http.post<Company>('/api/v1/companies', data));
  }
  async remove(id: string): Promise<void> {
    await this.auth.bootstrap();
    await firstValueFrom(this.http.delete(`/api/v1/companies/${id}`));
  }
}
