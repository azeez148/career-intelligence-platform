import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { resourceError } from '../resource-errors';
import { EmploymentType, JobFilters, JobSummary, WorkMode, employmentTypes, workModes } from './job-model';
import { JobService } from './job.service';

@Component({
  selector: 'app-job-list', imports: [DatePipe, FormsModule, RouterLink],
  template: `
    <section class="resource-panel"><h1>Jobs</h1>
      <p>Jobs extracted from your companies' public career sources. Values the source did not state are shown as “Not stated”.</p>
      <form class="job-filters" (ngSubmit)="applyFilters()">
        <label for="job-search">Search title or department</label>
        <input id="job-search" name="q" maxlength="100" [(ngModel)]="filters.q" />
        <label for="job-work-mode">Work mode</label>
        <select id="job-work-mode" name="workMode" [(ngModel)]="filters.work_mode">
          <option [ngValue]="undefined">Any work mode</option>
          @for (mode of modeOptions; track mode) { <option [ngValue]="mode">{{ workModes[mode] }}</option> }
        </select>
        <label for="job-employment">Employment type</label>
        <select id="job-employment" name="employmentType" [(ngModel)]="filters.employment_type">
          <option [ngValue]="undefined">Any employment type</option>
          @for (type of typeOptions; track type) { <option [ngValue]="type">{{ employmentTypes[type] }}</option> }
        </select>
        <label for="job-status">Listing status</label>
        <select id="job-status" name="status" [(ngModel)]="filters.status">
          <option value="open">Open</option><option value="closed">Closed</option><option value="all">All</option>
        </select>
        <label class="checkbox"><input type="checkbox" name="duplicates" [(ngModel)]="filters.include_duplicates" />
          Include copies found through other sources</label>
        <button type="submit" [disabled]="loading()">Apply filters</button>
      </form>
      @if (filters.company_id || filters.source_id) {
        <p>Showing jobs for one {{ filters.source_id ? 'career source' : 'company' }}.
          <button type="button" class="link-button" (click)="clearScope()">Show all companies</button></p>
      }
      @if (error()) { <p role="alert">{{ error() }}</p> }
      @if (loading()) { <p role="status">Loading jobs…</p> }
      @for (job of items(); track job.id) {
        <article><h2><a [routerLink]="['/jobs', job.id]">{{ job.title }}</a></h2>
          <p>{{ job.company_name ?? 'Unnamed company' }}{{ job.department ? ' · ' + job.department : '' }}</p>
          <p>{{ job.location_text ?? 'Location not stated' }} · {{ workModes[job.work_mode] }} · {{ employmentTypes[job.employment_type] }}</p>
          <p><span class="status-pill">{{ job.confidence }} confidence</span>
            @if (job.closed_at) { <span class="status-pill closed">No longer listed</span> }
            @if (job.duplicate_of_job_id) { <span class="status-pill">Copy from another source</span> }
            Last seen {{ job.last_seen_at | date:'medium' }}</p>
        </article>
      } @empty { @if (!loading() && !error()) { <p>No jobs match these filters yet. Jobs appear after a discovery scan finds a supported career source.</p> } }
      <div class="actions">
        @if (next() !== null) { <button (click)="load(next() ?? 0)" [disabled]="loading()">Load more</button> }
        <button (click)="load()" [disabled]="loading()">Reload jobs</button>
      </div>
    </section>
  `,
})
export class JobList implements OnInit {
  private readonly api = inject(JobService);
  private readonly route = inject(ActivatedRoute);
  readonly workModes = workModes; readonly employmentTypes = employmentTypes;
  readonly modeOptions = Object.keys(workModes) as WorkMode[];
  readonly typeOptions = Object.keys(employmentTypes) as EmploymentType[];
  readonly items = signal<JobSummary[]>([]); readonly next = signal<number | null>(null);
  readonly loading = signal(false); readonly error = signal('');
  filters: JobFilters = { status: 'open', include_duplicates: false };
  ngOnInit(): void {
    const query = this.route.snapshot.queryParamMap;
    this.filters.company_id = query.get('company_id') ?? undefined;
    this.filters.source_id = query.get('source_id') ?? undefined;
    void this.load();
  }
  applyFilters(): void { void this.load(); }
  clearScope(): void { this.filters.company_id = undefined; this.filters.source_id = undefined; void this.load(); }
  async load(offset = 0): Promise<void> {
    this.loading.set(true); this.error.set('');
    const q = this.filters.q?.trim();
    try {
      const page = await this.api.list({ ...this.filters, q: q || undefined }, offset);
      this.items.set(offset ? [...this.items(), ...page.items] : page.items); this.next.set(page.next_offset);
    } catch (error) { this.error.set(resourceError(error)); }
    finally { this.loading.set(false); }
  }
}
