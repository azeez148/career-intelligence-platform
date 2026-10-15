import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AuthService } from '../auth/auth.service';
import { WorkMode, workModes } from '../jobs/job-model';
import { PreferenceService } from '../preferences/preference.service';
import { resourceError } from '../resource-errors';
import {
  DISCLAIMER, MatchFilters, MatchStatus, MatchStatusView, MatchSummary, coveragePercent, runText, scoreText,
} from './match-model';
import { MatchService } from './match.service';

type Tab = MatchStatus;

@Component({
  selector: 'app-match-list', imports: [FormsModule, RouterLink],
  template: `
    <section class="resource-panel"><h1>Matches{{ profileName() ? ' for ' + profileName() : '' }}</h1>
      <p class="disclaimer">{{ disclaimer }}</p>
      @if (status(); as current) {
        <div class="match-status" role="status"><span>{{ runText(current) }}</span>
          @if (canRecalculate()) {
            <button type="button" (click)="recalculate()" [disabled]="current.active || busy()">Recalculate matches</button>
          }
        </div>
      }
      <div class="tabs" role="tablist" aria-label="Match groups">
        @for (tab of tabs; track tab.value) {
          <button type="button" role="tab" [attr.aria-selected]="activeTab() === tab.value"
            [class.active]="activeTab() === tab.value" (click)="selectTab(tab.value)">{{ tab.label }}</button>
        }
      </div>
      <form class="job-filters" (ngSubmit)="load()">
        <label for="match-search">Search job titles</label>
        <input id="match-search" name="q" maxlength="100" [(ngModel)]="query" />
        <label for="match-work-mode">Work mode</label>
        <select id="match-work-mode" name="workMode" [(ngModel)]="workMode">
          <option [ngValue]="undefined">Any work mode</option>
          @for (mode of modeOptions; track mode) { <option [ngValue]="mode">{{ workModes[mode] }}</option> }
        </select>
        @if (activeTab() === 'eligible') {
          <label for="match-min-score">Minimum score</label>
          <input id="match-min-score" name="minScore" type="number" min="0" max="100" [(ngModel)]="minScore" />
        }
        <button type="submit" [disabled]="loading()">Apply filters</button>
      </form>
      @if (error()) { <p role="alert">{{ error() }}</p> }
      @if (loading()) { <p role="status">Loading matches…</p> }
      @for (match of items(); track match.job.id) {
        <article><h2><a [routerLink]="['/preferences', profileId, 'matches', match.job.id]">{{ match.job.title }}</a></h2>
          <p>{{ match.job.company_name ?? 'Unnamed company' }} · {{ match.job.location_text ?? 'Location not stated' }}</p>
          <p><span class="status-pill score-pill">{{ scoreText(match) }}</span>
            <span class="status-pill">{{ coveragePercent(match.coverage) }}% of your weighting evaluated</span>
            @if (match.limited) { <span class="status-pill closed">Limited information</span> }
          </p>
          <p>{{ match.summary }}</p>
        </article>
      } @empty { @if (!loading() && !error()) { <p>{{ emptyText() }}</p> } }
      <div class="actions">
        @if (next() !== null) { <button (click)="load(next() ?? 0)" [disabled]="loading()">Load more</button> }
        <a routerLink="/preferences">Back to preference profiles</a>
      </div>
    </section>
  `,
})
export class MatchList implements OnInit {
  private readonly api = inject(MatchService); private readonly preferences = inject(PreferenceService);
  private readonly auth = inject(AuthService); private timer?: ReturnType<typeof setTimeout>;
  readonly profileId = inject(ActivatedRoute).snapshot.paramMap.get('id') ?? '';
  readonly disclaimer = DISCLAIMER; readonly workModes = workModes; readonly runText = runText;
  readonly scoreText = scoreText; readonly coveragePercent = coveragePercent;
  readonly modeOptions = Object.keys(workModes) as WorkMode[];
  readonly tabs: { value: Tab; label: string }[] = [
    { value: 'eligible', label: 'Ranked' }, { value: 'excluded', label: 'Excluded' },
    { value: 'insufficient_information', label: 'Not enough information' },
  ];
  readonly items = signal<MatchSummary[]>([]); readonly next = signal<number | null>(null);
  readonly status = signal<MatchStatusView | null>(null); readonly profileName = signal('');
  readonly activeTab = signal<Tab>('eligible'); readonly loading = signal(false);
  readonly busy = signal(false); readonly error = signal('');
  query = ''; workMode?: WorkMode; minScore: number | null = null;
  constructor() { inject(DestroyRef).onDestroy(() => this.stopPolling()); }
  ngOnInit(): void {
    void this.preferences.get(this.profileId).then(profile => this.profileName.set(profile.name), () => undefined);
    void this.load(); void this.refreshStatus();
  }
  canRecalculate(): boolean { return this.auth.user()?.permissions.includes('matches:update:self') ?? false; }
  emptyText(): string {
    if (this.activeTab() === 'excluded') return 'No jobs were excluded by your preferences.';
    if (this.activeTab() === 'insufficient_information') return 'Every job had enough information to evaluate.';
    return 'No matches yet. Matches appear after jobs are extracted for your companies.';
  }
  selectTab(tab: Tab): void { this.activeTab.set(tab); void this.load(); }
  filters(): MatchFilters {
    return {
      status: this.activeTab(), q: this.query.trim() || undefined, work_mode: this.workMode,
      min_score: this.activeTab() === 'eligible' && this.minScore !== null ? this.minScore : undefined,
    };
  }
  async load(offset = 0): Promise<void> {
    this.loading.set(true); this.error.set('');
    try {
      const page = await this.api.list(this.profileId, this.filters(), offset);
      this.items.set(offset ? [...this.items(), ...page.items] : page.items); this.next.set(page.next_offset);
    } catch (error) { this.error.set(resourceError(error)); }
    finally { this.loading.set(false); }
  }
  async recalculate(): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true); this.error.set('');
    try { await this.api.recalculate(this.profileId); await this.refreshStatus(); }
    catch (error) { this.error.set(resourceError(error)); }
    finally { this.busy.set(false); }
  }
  async refreshStatus(): Promise<void> {
    this.stopPolling();
    const wasActive = this.status()?.active ?? false;
    try {
      const current = await this.api.status(this.profileId); this.status.set(current);
      if (current.active) this.timer = setTimeout(() => void this.refreshStatus(), 3000);
      else if (wasActive) await this.load();
    } catch (error) { this.error.set(resourceError(error)); }
  }
  private stopPolling(): void { if (this.timer) clearTimeout(this.timer); this.timer = undefined; }
}
