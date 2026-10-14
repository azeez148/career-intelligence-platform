import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService, safeReturnUrl } from './auth.service';

export function authError(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    if (error.status === 401) return 'Email or password is incorrect, or your session has expired.';
    if (error.status === 403) return 'This action is not permitted. Reload the page and try again.';
    if (error.status === 409) return 'This email is already registered. Please sign in.';
    if (error.status === 429) return 'Too many attempts. Please wait before trying again.';
    if (error.status === 422) return 'Check the form values and try again.';
  }
  return 'The service is unavailable. Please try again.';
}

@Component({
  selector: 'app-credentials', imports: [ReactiveFormsModule, RouterLink],
  template: `
    <section class="account-panel">
      <h1>{{ registration ? 'Create an account' : 'Sign in' }}</h1>
      @if (route.snapshot.queryParamMap.get('registered')) { <p role="status">Account created. Sign in to continue.</p> }
      @if (error()) { <p role="alert">{{ error() }}</p> }
      <form [formGroup]="form" (ngSubmit)="submit()">
        @if (registration) {
          <label for="display-name">Display name</label>
          <input id="display-name" formControlName="display_name" autocomplete="name" maxlength="100" />
        }
        <label for="email">Email</label>
        <input id="email" type="email" formControlName="email" autocomplete="username" maxlength="320" required />
        <label for="password">Password</label>
        <input id="password" type="password" formControlName="password"
          [autocomplete]="registration ? 'new-password' : 'current-password'"
          aria-describedby="password-help" minlength="15" maxlength="128" required />
        <p id="password-help">Use 15–128 characters. Spaces are allowed.</p>
        @if (form.invalid && form.touched) { <p role="alert">Enter a valid email, password, and display name where required.</p> }
        <button type="submit" [disabled]="busy()">{{ busy() ? 'Please wait…' : registration ? 'Create account' : 'Sign in' }}</button>
      </form>
      <a [routerLink]="registration ? '/login' : '/register'">{{ registration ? 'Already registered? Sign in' : 'Create an account' }}</a>
    </section>
  `,
})
export class Credentials {
  readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly auth = inject(AuthService);
  readonly registration = this.route.snapshot.data['registration'] === true;
  readonly busy = signal(false);
  readonly error = signal('');
  readonly form = inject(FormBuilder).nonNullable.group({
    email: ['', [Validators.required, Validators.email, Validators.maxLength(320)]],
    password: ['', [Validators.required, Validators.minLength(15), Validators.maxLength(128)]],
    display_name: ['', this.registration ? [Validators.required, Validators.maxLength(100), Validators.pattern(/\S/)] : []],
  });

  async submit(): Promise<void> {
    this.form.markAllAsTouched();
    if (this.form.invalid || this.busy()) return;
    this.busy.set(true); this.error.set('');
    const { email, password, display_name } = this.form.getRawValue();
    try {
      if (this.registration) {
        await this.auth.register(email, password, display_name);
        await this.router.navigate(['/login'], { queryParams: { registered: '1' } });
      } else {
        await this.auth.login(email, password);
        await this.router.navigateByUrl(safeReturnUrl(this.route.snapshot.queryParamMap.get('returnUrl')));
      }
    } catch (error) { this.error.set(authError(error)); }
    finally { this.form.controls.password.reset(); this.form.markAsUntouched(); this.busy.set(false); }
  }
}
