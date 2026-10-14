import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService } from '../auth/auth.service';
import { resourceError } from '../resource-errors';
import { ScanSummary } from '../scans/scan-model';
import { ScanService } from '../scans/scan.service';
import { Company, CompanyService } from './company.service';

@Component({
  selector: 'app-company-list', imports: [RouterLink],
  template: `
    <section class="resource-panel"><h1>Your companies</h1>
      <p>Saved company details remain unverified until discovery records a public career source.</p>
      @if (can('create')) { <a routerLink="/companies/new">Add company</a> }
      @if (saved) { <p role="status">Company saved.</p> }
      @if (error()) { <p role="alert">{{ error() }}</p> }
      @if (loading()) { <p role="status">Loading companies…</p> }
      @for (company of items(); track company.id) {
        <article><h2>{{ company.display_label }}</h2>
          @if (company.website_url) { <p class="source-url">Website: {{ company.website_url }}</p> }
          @if (company.careers_url) { <p class="source-url">Careers: {{ company.careers_url }}</p> }
          @if (lastScans()[company.id]; as scan) { <p>Last discovery: {{ scan.status }}</p> }
          @else { <p>Unverified source</p> }
          <div class="actions">
          @if (canScan('create')) { <button type="button" (click)="discover(company)" [disabled]="busy()">Discover careers</button> }
          @if (lastScans()[company.id]; as scan) { <a [routerLink]="['/scans', scan.id]">View latest scan</a> }
          @if (can('update')) { <a [routerLink]="['/companies', company.id, 'edit']">Edit company</a> }
          @if (can('delete')) { <button type="button" (click)="remove(company)" [disabled]="busy()">Delete company</button> }
          </div>
        </article>
      } @empty { @if (!loading() && !error()) { <p>No companies saved yet.</p> } }
      <div class="actions">
        @if (next() !== null) { <button (click)="load(next() ?? 0)" [disabled]="loading() || busy()">Load more</button> }
        <button (click)="load()" [disabled]="loading() || busy()">Reload companies</button>
      </div>
    </section>
  `,
})
export class CompanyList implements OnInit {
  private readonly api = inject(CompanyService);
  private readonly scans = inject(ScanService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  readonly saved = inject(ActivatedRoute).snapshot.queryParamMap.has('saved');
  readonly items = signal<Company[]>([]);
  readonly next = signal<number | null>(null);
  readonly loading = signal(false);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly lastScans = signal<Record<string, ScanSummary | undefined>>({});
  can(action: string): boolean { return this.auth.user()?.permissions.includes(`companies:${action}:self`) ?? false; }
  canScan(action: string): boolean { return this.auth.user()?.permissions.includes(`scans:${action}:self`) ?? false; }
  ngOnInit(): void { void this.load(); }
  async load(offset = 0): Promise<void> {
    this.loading.set(true); this.error.set('');
    try {
      const page = await this.api.list(offset);
      this.items.set(offset ? [...this.items(), ...page.items] : page.items); this.next.set(page.next_offset);
      if (this.canScan('read')) {
        const results = await Promise.all(page.items.map(async company => [company.id,
          (await this.scans.list(0, company.id, undefined, 1)).items[0]] as const));
        this.lastScans.update(value => ({ ...value, ...Object.fromEntries(results) }));
      }
    } catch (error) { this.error.set(resourceError(error)); }
    finally { this.loading.set(false); }
  }
  async discover(company: Company): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true); this.error.set('');
    try { const scan = await this.scans.start(company.id); await this.router.navigate(['/scans', scan.id]); }
    catch (error) { this.error.set(resourceError(error)); }
    finally { this.busy.set(false); }
  }
  async remove(company: Company): Promise<void> {
    if (this.busy() || !window.confirm(`Delete ${company.display_label}? This cannot be undone.`)) return;
    this.busy.set(true); this.error.set('');
    try { await this.api.remove(company.id); await this.load(); }
    catch (error) { this.error.set(resourceError(error)); }
    finally { this.busy.set(false); }
  }
}
