import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService } from '../auth/auth.service';
import { ExtractionRun, isActive, runText, strategies } from '../jobs/job-model';
import { JobService } from '../jobs/job.service';
import { resourceError } from '../resource-errors';
import { CareerSource, DiscoveryCandidate, Scan, outcomeText } from './scan-model';
import { ScanService } from './scan.service';

@Component({
  selector: 'app-scan-detail', imports: [FormsModule, RouterLink],
  template: `
    <section class="resource-panel"><h1>Discovery scan</h1>
      @if (error()) { <p role="alert">{{ error() }}</p> }
      @if (loading() && !scan()) { <p role="status">Loading discovery scan…</p> }
      @if (scan(); as current) {
        <p><strong>Status:</strong> <span class="status-pill">{{ current.status }}</span></p>
        <p role="status">{{ outcomeText(current) }}</p>
        <p>Attempts: {{ current.attempt_count }}</p>
        @if (current.selected_url) { <p class="source-url">Selected URL: {{ current.selected_url }}</p> }
        @if (current.resolved_website_url) { <p class="source-url">Resolved website: {{ current.resolved_website_url }}</p> }
        @if (current.status === 'needs_input') {
          <h2>Confirm the official website</h2>
          @for (candidate of current.candidates; track candidate.id) {
            <article><p class="source-url">{{ candidate.url }}</p><p>Confidence: {{ candidate.confidence }}</p>
              <button (click)="choose(candidate)" [disabled]="saving()">Use this website</button></article>
          }
          <form (ngSubmit)="useManualUrl()">
            <label for="manual-website">Official website URL</label>
            <input id="manual-website" name="manualWebsite" type="url" [(ngModel)]="manualUrl" required />
            <button type="submit" [disabled]="saving()">Continue with URL</button>
          </form>
        }
        @if (current.sources.length) {
          <h2>Discovered career sources</h2>
          @for (source of current.sources; track source.id) {
            <article><p class="source-url">{{ source.url }}</p>
              <p>{{ source.platform ?? 'Generic career page' }} · {{ source.discovery_method }}</p>
              @if (runFor(source); as run) {
                <div class="extraction" [attr.aria-label]="'Job extraction for ' + source.url">
                  <p><strong>Jobs:</strong> <span class="status-pill">{{ run.status }}</span> {{ runText(run) }}</p>
                  @if (run.strategy) { <p>{{ strategies[run.strategy] }} · {{ run.confidence }} confidence</p> }
                  @if (run.status === 'succeeded' || run.status === 'partial') {
                    <p>{{ run.jobs_created }} new · {{ run.jobs_updated }} updated · {{ run.jobs_unchanged }} unchanged · {{ run.jobs_closed }} no longer listed</p>
                    <a [routerLink]="['/jobs']" [queryParams]="{ source_id: source.id }">View jobs from this source</a>
                  }
                </div>
              } @else { <p>Job extraction has not run for this source.</p> }
              @if (canExtract()) {
                <button (click)="reExtract(source)" [disabled]="extracting() === source.id || isRunActive(source)">Re-extract jobs</button>
              }
            </article>
          }
        }
        <div class="actions"><button (click)="load()" [disabled]="loading() || saving()">Refresh status</button>
          <a routerLink="/scans">Back to scan history</a></div>
      }
    </section>
  `,
})
export class ScanDetail implements OnInit {
  private readonly api = inject(ScanService); private readonly route = inject(ActivatedRoute);
  private readonly jobs = inject(JobService); private readonly auth = inject(AuthService);
  private readonly router = inject(Router); private timer?: ReturnType<typeof setTimeout>;
  readonly scan = signal<Scan | null>(null); readonly loading = signal(false);
  readonly saving = signal(false); readonly error = signal(''); readonly outcomeText = outcomeText;
  readonly extracting = signal<string | null>(null); readonly runText = runText; readonly strategies = strategies;
  manualUrl = '';
  constructor() { inject(DestroyRef).onDestroy(() => this.stopPolling()); }
  ngOnInit(): void { void this.load(); }
  async load(): Promise<void> {
    this.stopPolling(); this.loading.set(true); this.error.set('');
    try { this.scan.set(await this.api.get(this.route.snapshot.paramMap.get('id') ?? '')); }
    catch (error) { this.error.set(resourceError(error)); }
    finally { this.loading.set(false); this.schedulePolling(); }
  }
  async choose(candidate: DiscoveryCandidate): Promise<void> { await this.select({ candidate_id: candidate.id }); }
  async useManualUrl(): Promise<void> {
    const value = this.manualUrl.trim(); if (value) await this.select({ website_url: value });
  }
  private async select(selection: { candidate_id?: string; website_url?: string }): Promise<void> {
    const current = this.scan(); if (!current || this.saving()) return;
    this.saving.set(true); this.error.set('');
    try {
      const child = await this.api.select(current.id, selection); this.scan.set(child);
      await this.router.navigate(['/scans', child.id]); this.schedulePolling();
    } catch (error) { this.error.set(resourceError(error)); }
    finally { this.saving.set(false); }
  }
  runFor(source: CareerSource): ExtractionRun | undefined {
    return this.scan()?.extractions?.find(run => run.source_id === source.id);
  }
  isRunActive(source: CareerSource): boolean { const run = this.runFor(source); return !!run && isActive(run); }
  canExtract(): boolean { return this.auth.user()?.permissions.includes('extractions:create:self') ?? false; }
  async reExtract(source: CareerSource): Promise<void> {
    const current = this.scan(); if (!current || this.extracting()) return;
    this.extracting.set(source.id); this.error.set('');
    try {
      const run = await this.jobs.extract(source.id);
      const latest = this.scan() ?? current;
      const others = (latest.extractions ?? []).filter(row => row.source_id !== source.id);
      this.scan.set({ ...latest, extractions: [...others, run] });
      this.stopPolling(); this.schedulePolling();
    } catch (error) { this.error.set(resourceError(error)); }
    finally { this.extracting.set(null); }
  }
  private schedulePolling(): void {
    const current = this.scan();
    if (['queued', 'running'].includes(current?.status ?? '') || (current?.extractions ?? []).some(isActive)) {
      this.timer = setTimeout(() => void this.load(), 3000);
    }
  }
  private stopPolling(): void { if (this.timer) clearTimeout(this.timer); this.timer = undefined; }
}
