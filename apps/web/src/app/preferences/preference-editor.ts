import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { resourceError } from '../resource-errors';
import { Criteria, RemotePolicy, criteriaError, entries, listFields, weightFields } from './preference-model';
import { PreferenceService } from './preference.service';

@Component({
  selector: 'app-preference-editor', imports: [ReactiveFormsModule, RouterLink],
  template: `
    <section class="resource-panel"><h1>{{ id ? 'Edit preference profile' : 'Add preference profile' }}</h1>
      @if (loading()) { <p role="status">Loading preference profile…</p> }
      @if (error()) { <p role="alert" id="preference-errors" tabindex="-1">{{ error() }}</p> }
      @if (loadFailed()) { <button (click)="load()">Retry loading preference profile</button> }
      <form [formGroup]="form" (ngSubmit)="save()">
        <fieldset [disabled]="loading() || loadFailed() || busy()">
          <legend>Search criteria</legend>
          <label for="preference-name">Profile name</label><input id="preference-name" formControlName="name" maxlength="100" required />
          <p id="list-help">Enter one item per line. Empty lines are ignored. Maximum 50 items per list, 100 characters each, and 200 items overall. Your choices are saved without a predefined catalog.</p>
          @for (field of lists; track field.key) {
            <label [for]="field.key">{{ field.label }}</label>
            <textarea [id]="field.key" [formControlName]="field.key" aria-describedby="list-help" maxlength="5200"></textarea>
          }
          <label for="remote-policy">Remote-work preference</label>
          <select id="remote-policy" formControlName="remote_policy">
            <option value="any">Any work arrangement</option><option value="remote_only">Remote only</option><option value="exclude_remote">Exclude remote</option>
          </select>
          <p>Locations may still apply to remote roles. Leave experience bounds empty if unrestricted.</p>
          <label for="minimum-months">Minimum experience (months)</label><input id="minimum-months" type="number" formControlName="experience_min_months" min="0" max="1200" step="1" />
          <label for="maximum-months">Maximum experience (months)</label><input id="maximum-months" type="number" formControlName="experience_max_months" min="0" max="1200" step="1" />
          <fieldset formGroupName="weights"><legend>Matching weights</legend>
            <p id="weights-help">Allocate 100 points across factors with criteria. Required skills and exclusions are stored separately. Matching is not run in this phase.</p>
            @for (field of weights; track field.key) {
              <label [for]="'weight-' + field.key">{{ field.label }} weight</label>
              <input [id]="'weight-' + field.key" type="number" [formControlName]="field.key" min="0" max="100" step="1" required aria-describedby="weights-help weight-total" />
            }
            <p id="weight-total" aria-live="polite">Allocated: {{ weightTotal() }} / 100</p>
          </fieldset>
          <button type="submit">{{ busy() ? 'Saving…' : 'Save preference profile' }}</button>
        </fieldset>
      </form><a routerLink="/preferences">Back to preference profiles</a>
    </section>
  `,
})
export class PreferenceEditor implements OnInit {
  readonly id = inject(ActivatedRoute).snapshot.paramMap.get('id');
  private readonly api = inject(PreferenceService);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);
  readonly lists = listFields;
  readonly weights = weightFields;
  readonly loading = signal(false);
  readonly loadFailed = signal(false);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly form = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(100), Validators.pattern(/\S/)]],
    preferred_skills: [''], required_skills: [''], preferred_keywords: [''], excluded_keywords: [''],
    job_titles: [''], seniority_preferences: [''], locations: [''], employment_types: [''],
    remote_policy: ['any' as RemotePolicy],
    experience_min_months: this.fb.control<number | null>(null), experience_max_months: this.fb.control<number | null>(null),
    weights: this.fb.nonNullable.group({ skills: [0], title: [0], location: [0], experience: [0], employment: [0], keywords: [0] }),
  });
  ngOnInit(): void { if (this.id) void this.load(); }
  weightTotal(): number { return Object.values(this.form.controls.weights.getRawValue()).reduce((sum, value) => sum + (value || 0), 0); }
  async load(): Promise<void> {
    if (!this.id) return;
    this.loading.set(true); this.loadFailed.set(false); this.error.set('');
    try {
      const profile = await this.api.get(this.id);
      const c = profile.criteria;
      this.form.patchValue({ name: profile.name, remote_policy: c.remote_policy, experience_min_months: c.experience_min_months,
        experience_max_months: c.experience_max_months, weights: c.weights });
      for (const field of this.lists) this.form.controls[field.key].setValue(c[field.key].join('\n'));
    } catch (error) { this.error.set(resourceError(error)); this.loadFailed.set(true); }
    finally { this.loading.set(false); }
  }
  async save(): Promise<void> {
    if (this.busy() || this.loading() || this.loadFailed()) return;
    this.form.markAllAsTouched();
    const v = this.form.getRawValue();
    const criteria: Criteria = { preferred_skills: entries(v.preferred_skills), required_skills: entries(v.required_skills),
      preferred_keywords: entries(v.preferred_keywords), excluded_keywords: entries(v.excluded_keywords),
      job_titles: entries(v.job_titles), seniority_preferences: entries(v.seniority_preferences),
      locations: entries(v.locations), employment_types: entries(v.employment_types), remote_policy: v.remote_policy,
      experience_min_months: v.experience_min_months, experience_max_months: v.experience_max_months, weights: v.weights };
    const problem = this.form.invalid ? 'Enter a profile name of 1–100 characters.' : criteriaError(criteria);
    if (problem) { this.error.set(problem); return; }
    this.busy.set(true); this.error.set('');
    try {
      await this.api.save({ name: v.name.trim(), criteria }, this.id);
      await this.router.navigate(['/preferences'], { queryParams: { saved: '1' } });
    } catch (error) { this.error.set(resourceError(error)); }
    finally { this.busy.set(false); }
  }
}
