import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { AuthService } from './auth.service';
import { authError } from './credentials';

@Component({
  selector: 'app-profile', imports: [ReactiveFormsModule],
  template: `
    <section class="account-panel">
      <h1>Your profile</h1><p>{{ auth.user()?.email }}</p>
      @if (message()) { <p role="status">{{ message() }}</p> }
      <form [formGroup]="form" (ngSubmit)="save()">
        <label for="profile-name">Display name</label>
        <input id="profile-name" formControlName="display_name" maxlength="100" required />
        <label for="bio">About you</label><textarea id="bio" formControlName="bio" maxlength="2000"></textarea>
        <button [disabled]="busy() || !auth.user()?.permissions?.includes('profile:update:self')">Save profile</button>
      </form>
    </section>
  `,
})
export class Profile {
  readonly auth = inject(AuthService);
  readonly busy = signal(false);
  readonly message = signal('');
  readonly form = inject(FormBuilder).nonNullable.group({
    display_name: [this.auth.user()?.display_name ?? '', [Validators.required, Validators.maxLength(100), Validators.pattern(/\S/)]],
    bio: [this.auth.user()?.bio ?? '', Validators.maxLength(2000)],
  });
  async save(): Promise<void> {
    if (this.form.invalid) { this.message.set('Enter a display name of 1–100 characters and a bio of up to 2000 characters.'); return; }
    if (this.busy()) return;
    this.busy.set(true);
    try {
      const { display_name, bio } = this.form.getRawValue();
      await this.auth.saveProfile(display_name, bio); this.message.set('Profile saved.');
    } catch (error) { this.message.set(authError(error)); }
    finally { this.busy.set(false); }
  }
}
