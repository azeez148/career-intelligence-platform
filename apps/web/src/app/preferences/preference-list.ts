import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AuthService } from '../auth/auth.service';
import { resourceError } from '../resource-errors';
import { PreferenceSummary } from './preference-model';
import { PreferenceService } from './preference.service';

@Component({
  selector: 'app-preference-list', imports: [RouterLink],
  template: `
    <section class="resource-panel"><h1>Your preference profiles</h1>
      <p>Keep separate profiles for different searches. Matching scores are not calculated yet.</p>
      @if (can('create')) { <a routerLink="/preferences/new">Add preference profile</a> }
      @if (saved) { <p role="status">Preference profile saved.</p> }
      @if (error()) { <p role="alert">{{ error() }}</p> }
      @if (loading()) { <p role="status">Loading preference profiles…</p> }
      @for (profile of items(); track profile.id) {
        <article><h2>{{ profile.name }}</h2><div class="actions">
          @if (can('update')) { <a [routerLink]="['/preferences', profile.id, 'edit']">Edit preference profile</a> }
          @if (can('delete')) { <button (click)="remove(profile)" [disabled]="busy()">Delete preference profile</button> }
        </div></article>
      } @empty { @if (!loading() && !error()) { <p>No preference profiles saved yet.</p> } }
      <div class="actions">
        @if (next() !== null) { <button (click)="load(next() ?? 0)" [disabled]="loading() || busy()">Load more</button> }
        <button (click)="load()" [disabled]="loading() || busy()">Reload preference profiles</button>
      </div>
    </section>
  `,
})
export class PreferenceList implements OnInit {
  private readonly api = inject(PreferenceService);
  private readonly auth = inject(AuthService);
  readonly saved = inject(ActivatedRoute).snapshot.queryParamMap.has('saved');
  readonly items = signal<PreferenceSummary[]>([]);
  readonly next = signal<number | null>(null);
  readonly loading = signal(false);
  readonly busy = signal(false);
  readonly error = signal('');
  can(action: string): boolean { return this.auth.user()?.permissions.includes(`preferences:${action}:self`) ?? false; }
  ngOnInit(): void { void this.load(); }
  async load(offset = 0): Promise<void> {
    this.loading.set(true); this.error.set('');
    try {
      const page = await this.api.list(offset);
      this.items.set(offset ? [...this.items(), ...page.items] : page.items); this.next.set(page.next_offset);
    } catch (error) { this.error.set(resourceError(error)); }
    finally { this.loading.set(false); }
  }
  async remove(profile: PreferenceSummary): Promise<void> {
    if (this.busy() || !window.confirm(`Delete ${profile.name}? This cannot be undone.`)) return;
    this.busy.set(true); this.error.set('');
    try { await this.api.remove(profile.id); await this.load(); }
    catch (error) { this.error.set(resourceError(error)); }
    finally { this.busy.set(false); }
  }
}
