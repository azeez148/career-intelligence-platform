import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { resourceError } from '../resource-errors';
import { Job, confidenceText, employmentTypes, strategies, workModes } from './job-model';
import { JobService } from './job.service';

@Component({
  selector: 'app-job-detail', imports: [DatePipe, RouterLink],
  template: `
    <section class="resource-panel">
      @if (error()) { <h1>Job</h1><p role="alert">{{ error() }}</p> }
      @if (loading() && !job()) { <p role="status">Loading job…</p> }
      @if (job(); as current) {
        <h1>{{ current.title }}</h1>
        <p>{{ current.company_name ?? 'Unnamed company' }}</p>
        @if (current.closed_at) { <p class="status-pill closed">No longer listed since {{ current.closed_at | date:'mediumDate' }}</p> }
        <dl class="job-facts">
          <dt>Location</dt><dd>{{ current.location_text ?? 'Not stated' }}</dd>
          <dt>Work mode</dt><dd>{{ workModes[current.work_mode] }}</dd>
          <dt>Employment type</dt><dd>{{ employmentTypes[current.employment_type] }}</dd>
          <dt>Department</dt><dd>{{ current.department ?? 'Not stated' }}</dd>
          <dt>Posted</dt><dd>{{ current.posted_at ? (current.posted_at | date:'mediumDate') : 'Not stated' }}</dd>
          <dt>Apply by</dt><dd>{{ current.valid_through ? (current.valid_through | date:'mediumDate') : 'Not stated' }}</dd>
        </dl>
        <p><a class="source-url" [href]="current.canonical_url" target="_blank" rel="noopener noreferrer nofollow">View on the source site</a></p>
        <h2>Description</h2>
        @if (current.description_text) { <p class="job-text">{{ current.description_text }}</p> }
        @else { <p>The source did not provide a description.</p> }
        <h2>Requirements</h2>
        @if (current.requirements_text) { <p class="job-text">{{ current.requirements_text }}</p> }
        @else { <p>No requirements section was identified. Check the source page.</p> }
        <h2>Where this came from</h2>
        <p>{{ strategies[current.extraction_method] }}. {{ confidenceText[current.confidence] }}</p>
        <p>First seen {{ current.first_seen_at | date:'medium' }} · last seen {{ current.last_seen_at | date:'medium' }}</p>
        @if (heuristicFields(current).length) {
          <p>Inferred from page layout: {{ heuristicFields(current).join(', ') }}.</p>
        }
        @if (current.duplicate_of_job_id) {
          <p>This is a copy of a job also found through another source. <a [routerLink]="['/jobs', current.duplicate_of_job_id]">View the primary listing</a></p>
        }
      }
      <div class="actions"><a routerLink="/jobs">Back to jobs</a></div>
    </section>
  `,
})
export class JobDetail implements OnInit {
  private readonly api = inject(JobService); private readonly route = inject(ActivatedRoute);
  readonly job = signal<Job | null>(null); readonly loading = signal(false); readonly error = signal('');
  readonly workModes = workModes; readonly employmentTypes = employmentTypes;
  readonly strategies = strategies; readonly confidenceText = confidenceText;
  private readonly labels: Record<string, string> = {
    title: 'title', description_text: 'description', requirements_text: 'requirements',
  };
  ngOnInit(): void { this.route.paramMap.subscribe(params => void this.load(params.get('id') ?? '')); }
  async load(id: string): Promise<void> {
    this.loading.set(true); this.error.set(''); this.job.set(null);
    try { this.job.set(await this.api.get(id)); }
    catch (error) { this.error.set(resourceError(error)); }
    finally { this.loading.set(false); }
  }
  heuristicFields(job: Job): string[] {
    return Object.entries(job.field_sources)
      .filter(([, kind]) => kind === 'heuristic').map(([field]) => this.labels[field] ?? field);
  }
}
