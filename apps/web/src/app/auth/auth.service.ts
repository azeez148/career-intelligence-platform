import { HttpBackend, HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export interface User {
  id: string;
  email: string;
  display_name: string;
  bio: string;
  permissions: string[];
}
export interface Session {
  id: string;
  created_at: string;
  expires_at: string;
  current: boolean;
}
export interface SessionPage { items: Session[]; next_offset: number | null }

export function safeReturnUrl(value: string | null): string {
  const account = /^\/(profile|sessions)(\?.*)?$/;
  const resource = /^\/(companies|preferences)(?:\/new|\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/edit)?(?:\?.*)?$/i;
  return value && (account.test(value) || resource.test(value)) ? value : '/profile';
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly raw = new HttpClient(inject(HttpBackend));
  readonly user = signal<User | null>(null);
  readonly ready = signal(false);
  private refreshFlight?: Promise<void>;
  private loadFlight?: Promise<void>;
  private readonly channel = typeof BroadcastChannel !== 'undefined'
    ? new BroadcastChannel('career-session') : null;

  constructor() {
    if (this.channel) this.channel.onmessage = (event: MessageEvent<unknown>) => {
      if (event.data === 'logout') { this.user.set(null); this.ready.set(true); }
      if (event.data === 'login') { this.ready.set(false); }
    };
  }

  async load(): Promise<void> {
    if (this.ready()) return;
    if (!this.loadFlight) this.loadFlight = this.fetchUser().finally(() => {
      this.loadFlight = undefined;
    });
    return this.loadFlight;
  }

  private async fetchUser(): Promise<void> {
    try {
      this.user.set(await firstValueFrom(this.http.get<User>('/api/v1/users/me')));
      this.ready.set(true);
    } catch (error) {
      if (error instanceof HttpErrorResponse && error.status === 401) {
        this.user.set(null); this.ready.set(true);
      } else throw error;
    }
  }

  async bootstrap(): Promise<void> {
    await firstValueFrom(this.http.get('/api/v1/auth/csrf', { responseType: 'text' }));
  }

  async register(email: string, password: string, display_name: string): Promise<void> {
    await this.bootstrap();
    await firstValueFrom(this.http.post('/api/v1/auth/register', { email, password, display_name }));
  }

  async login(email: string, password: string): Promise<void> {
    await this.bootstrap();
    const result = await firstValueFrom(this.http.post<{ user: User }>('/api/v1/auth/login', { email, password }));
    this.user.set(result.user); this.ready.set(true);
    this.channel?.postMessage('login');
  }

  async refresh(): Promise<void> {
    if (!this.refreshFlight) {
      const rotate = async () => {
        // A different tab may have refreshed while this tab waited for the lock.
        try {
          await firstValueFrom(this.raw.get('/api/v1/users/me'));
          return;
        } catch (error) {
          if (!(error instanceof HttpErrorResponse) || error.status !== 401) throw error;
        }
        await this.bootstrap();
        await firstValueFrom(this.http.post('/api/v1/auth/refresh', {}));
      };
      this.refreshFlight = (navigator.locks
        ? navigator.locks.request('career-refresh', rotate) : rotate())
        .catch((error: unknown) => {
          if (error instanceof HttpErrorResponse && error.status === 401) {
            this.user.set(null); this.ready.set(true);
          }
          throw error;
        }).finally(() => { this.refreshFlight = undefined; });
    }
    return this.refreshFlight;
  }

  async logout(all = false): Promise<void> {
    await this.bootstrap();
    await firstValueFrom(this.http.post(`/api/v1/auth/${all ? 'logout-all' : 'logout'}`, {}));
    this.forget();
  }

  forget(): void {
    this.user.set(null); this.ready.set(true); this.channel?.postMessage('logout');
  }

  async saveProfile(display_name: string, bio: string): Promise<void> {
    await this.bootstrap();
    this.user.set(await firstValueFrom(this.http.patch<User>('/api/v1/users/me/profile', { display_name, bio })));
  }

  async sessions(offset = 0): Promise<SessionPage> {
    return firstValueFrom(this.http.get<SessionPage>(`/api/v1/auth/sessions?offset=${offset}`));
  }

  async revoke(id: string): Promise<void> {
    await this.bootstrap();
    await firstValueFrom(this.http.delete(`/api/v1/auth/sessions/${id}`));
  }
}
