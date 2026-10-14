import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { resourceError } from '../resource-errors';
import { ScanStatus, ScanSummary } from './scan-model';
import { ScanService } from './scan.service';

@Component({
  selector: 'app-scan-list', imports: [DatePipe, FormsModule, RouterLink],
  template: `
    <section class="resource-panel"><h1>Discovery scans</h1>
      <p>Review persisted career-source discovery history. Scans do not extract job listings.</p>
      <form class="scan-filters" (ngSubmit)="applyFilters()">
        <label for="scan-company">Company ID</label>
        <input id="scan-company" name="company" [(ngModel)]="companyFilter" />
        <label for="scan-status">Status</label>
        <select id="scan-status" name="status" [(ngModel)]="statusFilter">
          <option value="">All statuses</option>
          @for (status of statuses; track status) { <option [value]="status">{{ status }}</option> }
        </select>
        <button type="submit" [disabled]="loading()">Apply filters</button>
      </form>
      @if (error()) { <p role="alert">{{ error() }}</p> }
      @if (loading()) { <p role="status">Loading discovery scans…</p> }
      @for (scan of items(); track scan.id) {
        <article><h2>Scan {{ scan.created_at | date:'medium' }}</h2>
          <p><strong>Status:</strong> {{ scan.status }}</p>
          <p class="source-url"><strong>Selected URL:</strong> {{ scan.selected_url ?? 'Awaiting selection' }}</p>
          <a [routerLink]="['/scans', scan.id]">View scan details</a>
        </article>
      } @empty { @if (!loading() && !error()) { <p>No discovery scans found.</p> } }
      <div class="actions">
        @if (next() !== null) { <button (click)="load(next() ?? 0)" [disabled]="loading()">Load more</button> }
        <button (click)="load()" [disabled]="loading()">Reload scans</button>
      </div>
    </section>
  `,
})
export class ScanList implements OnInit {
  private readonly api = inject(ScanService);
  private readonly route = inject(ActivatedRoute);
  readonly statuses: ScanStatus[] = ['queued', 'running', 'needs_input', 'succeeded', 'unsupported', 'failed', 'superseded'];
  readonly items = signal<ScanSummary[]>([]); readonly next = signal<number | null>(null);
  readonly loading = signal(false); readonly error = signal('');
  companyFilter = ''; statusFilter = '';
  ngOnInit(): void { this.companyFilter = this.route.snapshot.queryParamMap.get('company_id') ?? ''; void this.load(); }
  applyFilters(): void { void this.load(); }
  async load(offset = 0): Promise<void> {
    this.loading.set(true); this.error.set('');
    try {
      const page = await this.api.list(offset, this.companyFilter.trim() || undefined,
        (this.statusFilter || undefined) as ScanStatus | undefined);
      this.items.set(offset ? [...this.items(), ...page.items] : page.items); this.next.set(page.next_offset);
    } catch (error) { this.error.set(resourceError(error)); }
    finally { this.loading.set(false); }
  }
}
