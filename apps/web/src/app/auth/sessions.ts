import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService, Session } from './auth.service';
import { authError } from './credentials';

@Component({
  selector: 'app-sessions', imports: [DatePipe],
  template: `
    <section class="account-panel"><h1>Your sessions</h1>
      @if (message()) { <p role="status">{{ message() }}</p> }
      @if (loading()) { <p role="status">Loading sessions…</p> }
      @for (session of items(); track session.id) {
        <article><h2>{{ session.current ? 'Current session' : 'Other session' }}</h2>
          <p>Signed in {{ session.created_at | date:'medium' }}</p>
          <p>Expires {{ session.expires_at | date:'medium' }}</p>
          <button [disabled]="busy()" (click)="revoke(session)">Revoke session</button>
        </article>
      } @empty { @if (!loading()) { <p>No active sessions found.</p> } }
      @if (next() !== null) { <button (click)="load(next() ?? 0)" [disabled]="loading()">Load more</button> }
      <button (click)="load()" [disabled]="loading()">Reload sessions</button>
      <button (click)="logoutAll()" [disabled]="busy()">Sign out everywhere</button>
    </section>
  `,
})
export class Sessions implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  readonly items = signal<Session[]>([]);
  readonly next = signal<number | null>(null);
  readonly message = signal('');
  readonly busy = signal(false);
  readonly loading = signal(false);
  ngOnInit(): void { void this.load(); }
  async load(offset = 0): Promise<void> {
    this.loading.set(true); this.message.set('');
    try {
      const page = await this.auth.sessions(offset);
      this.items.set(offset ? [...this.items(), ...page.items] : page.items); this.next.set(page.next_offset);
    } catch (error) { this.message.set(authError(error)); }
    finally { this.loading.set(false); }
  }
  async revoke(session: Session): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    try {
      await this.auth.revoke(session.id);
      if (session.current) { this.auth.forget(); await this.router.navigateByUrl('/login'); }
      else await this.load();
    } catch (error) { this.message.set(authError(error)); }
    finally { this.busy.set(false); }
  }
  async logoutAll(): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    try { await this.auth.logout(true); await this.router.navigateByUrl('/login'); }
    catch (error) { this.message.set(authError(error)); }
    finally { this.busy.set(false); }
  }
}
