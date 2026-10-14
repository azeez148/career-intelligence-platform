import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HealthService } from './health.service';

@Component({
  selector: 'app-foundation',
  template: `
    <p class="eyebrow">Development environment</p>
    <h1>Career Intelligence Platform</h1>
    <p class="intro">The foundation for discovering opportunities and understanding your fit.</p>
    <section aria-labelledby="status-heading">
      <h2 id="status-heading">Connection status</h2>
      <p role="status" aria-live="polite">
        @switch (state()) {
          @case ('loading') { Checking connection… }
          @case ('ready') { The application is connected and ready. }
          @case ('unavailable') { The service is temporarily unavailable. Please try again. }
        }
      </p>
      <button type="button" (click)="refresh()" [disabled]="state() === 'loading'">Check again</button>
    </section>
    <p class="note">Job discovery and matching will be available in a future phase.</p>
  `,
  styles: `
    .eyebrow { color: #245b50; font-size: .8rem; letter-spacing: .08em; text-transform: uppercase; }
    h1 { font-size: clamp(2rem, 5vw, 3.3rem); letter-spacing: -.04em; line-height: 1.12; }
    .intro { max-width: 38rem; color: #475569; font-size: 1.15rem; line-height: 1.7; }
    section { margin-top: 2.5rem; padding: 1.5rem; border: 1px solid #ccd8d3; border-radius: .75rem; background: white; }
    h2 { margin-top: 0; font-size: 1.1rem; }
    button { padding: .7rem 1rem; background: #245b50; color: white; border: 0; border-radius: .35rem; cursor: pointer; font: inherit; }
    button:disabled { opacity: .6; cursor: wait; }
    button:focus-visible { outline: 3px solid #1d4ed8; outline-offset: 3px; }
    .note { font-size: .9rem; color: #475569; margin-top: 1.5rem; }
  `,
})
export class Foundation {
  private readonly health = inject(HealthService);
  private readonly destroyRef = inject(DestroyRef);
  readonly state = signal<'loading' | 'ready' | 'unavailable'>('loading');

  constructor() { this.refresh(); }

  refresh(): void {
    this.state.set('loading');
    this.health.readiness().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (result) => this.state.set(result.status === 'ready' ? 'ready' : 'unavailable'),
      error: () => this.state.set('unavailable'),
    });
  }
}
