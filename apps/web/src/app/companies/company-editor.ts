import { Component, OnInit, inject, signal } from '@angular/core';
import { AbstractControl, FormBuilder, ReactiveFormsModule, ValidationErrors, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { resourceError } from '../resource-errors';
import { CompanyService } from './company.service';

function identity(control: AbstractControl): ValidationErrors | null {
  const values = control.value as { name: string; website_url: string; careers_url: string };
  return Object.values(values).some(value => value.trim()) ? null : { identity: true };
}

@Component({
  selector: 'app-company-editor', imports: [ReactiveFormsModule, RouterLink],
  template: `
    <section class="resource-panel"><h1>{{ id ? 'Edit company' : 'Add company' }}</h1>
      <p>Enter a name or URL. We store your input without verifying the company or fetching its website.</p>
      @if (loading()) { <p role="status">Loading company…</p> }
      @if (error()) { <p role="alert" id="company-errors" tabindex="-1">{{ error() }}</p> }
      @if (loadFailed()) { <button (click)="load()">Retry loading company</button> }
      <form [formGroup]="form" (ngSubmit)="save()" aria-describedby="company-help">
        <fieldset [disabled]="loading() || loadFailed() || busy()">
          <label for="company-name">Company name</label><input id="company-name" formControlName="name" maxlength="200" />
          <label for="website-url">Website URL</label><input id="website-url" type="url" formControlName="website_url" maxlength="2048" />
          <label for="careers-url">Careers URL</label><input id="careers-url" type="url" formControlName="careers_url" maxlength="2048" />
          <p id="company-help">URLs need http:// or https:// and a public DNS hostname. No credentials, fragments, or non-standard ports. An external careers hostname is allowed.</p>
          <button type="submit">{{ busy() ? 'Saving…' : 'Save company' }}</button>
        </fieldset>
      </form><a routerLink="/companies">Back to companies</a>
    </section>
  `,
})
export class CompanyEditor implements OnInit {
  readonly id = inject(ActivatedRoute).snapshot.paramMap.get('id');
  private readonly api = inject(CompanyService);
  private readonly router = inject(Router);
  readonly loading = signal(false);
  readonly loadFailed = signal(false);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly form = inject(FormBuilder).nonNullable.group({
    name: ['', Validators.maxLength(200)], website_url: ['', Validators.maxLength(2048)], careers_url: ['', Validators.maxLength(2048)],
  }, { validators: identity });
  ngOnInit(): void { if (this.id) void this.load(); }
  async load(): Promise<void> {
    if (!this.id) return;
    this.loading.set(true); this.loadFailed.set(false); this.error.set('');
    try {
      const company = await this.api.get(this.id);
      this.form.setValue({ name: company.name ?? '', website_url: company.website_url ?? '', careers_url: company.careers_url ?? '' });
    } catch (error) { this.error.set(resourceError(error)); this.loadFailed.set(true); }
    finally { this.loading.set(false); }
  }
  async save(): Promise<void> {
    if (this.busy() || this.loading() || this.loadFailed()) return;
    this.form.markAllAsTouched();
    if (this.form.invalid) { this.error.set('Enter a name or URL and keep values within their length limits.'); return; }
    this.busy.set(true); this.error.set('');
    const values = this.form.getRawValue();
    try {
      await this.api.save({ name: values.name.trim() || null, website_url: values.website_url || null, careers_url: values.careers_url || null }, this.id);
      await this.router.navigate(['/companies'], { queryParams: { saved: '1' } });
    } catch (error) { this.error.set(resourceError(error)); }
    finally { this.busy.set(false); }
  }
}
