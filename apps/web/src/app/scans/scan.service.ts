import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { AuthService } from '../auth/auth.service';
import { Scan, ScanPage, ScanSelection, ScanStatus } from './scan-model';

@Injectable({ providedIn: 'root' })
export class ScanService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);

  list(offset = 0, companyId?: string, status?: ScanStatus, limit = 20): Promise<ScanPage> {
    let params = new HttpParams().set('offset', offset).set('limit', limit);
    if (companyId) params = params.set('company_id', companyId);
    if (status) params = params.set('status', status);
    return firstValueFrom(this.http.get<ScanPage>('/api/v1/scans', { params }));
  }
  get(id: string): Promise<Scan> {
    return firstValueFrom(this.http.get<Scan>(`/api/v1/scans/${id}`));
  }
  async start(companyId: string): Promise<Scan> {
    await this.auth.bootstrap();
    return firstValueFrom(this.http.post<Scan>(`/api/v1/companies/${companyId}/scans`, {}));
  }
  async select(scanId: string, selection: ScanSelection): Promise<Scan> {
    await this.auth.bootstrap();
    return firstValueFrom(this.http.post<Scan>(`/api/v1/scans/${scanId}/selection`, selection));
  }
}
