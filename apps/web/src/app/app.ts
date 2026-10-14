import { Component, effect, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterOutlet } from '@angular/router';
import { AuthService } from './auth/auth.service';
import { authError } from './auth/credentials';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  readonly error = signal('');
  readonly busy = signal(false);
  constructor() {
    effect(() => {
      if (this.auth.ready() && !this.auth.user() && /^\/(profile|sessions)/.test(this.router.url)) {
        void this.router.navigateByUrl('/login');
      }
    });
  }
  async logout(): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true); this.error.set('');
    try { await this.auth.logout(); await this.router.navigateByUrl('/login'); }
    catch (error) { this.error.set(authError(error)); }
    finally { this.busy.set(false); }
  }
}
