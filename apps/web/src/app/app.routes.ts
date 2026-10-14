import { Routes } from '@angular/router';
import { Foundation } from './foundation';
import { authenticated, guest } from './auth/auth.guards';

export const routes: Routes = [
  { path: 'login', loadComponent: () => import('./auth/credentials').then(m => m.Credentials), canActivate: [guest], title: 'Sign in' },
  { path: 'register', loadComponent: () => import('./auth/credentials').then(m => m.Credentials), canActivate: [guest], data: { registration: true }, title: 'Create account' },
  { path: 'profile', loadComponent: () => import('./auth/profile').then(m => m.Profile), canActivate: [authenticated], data: { permission: 'profile:read:self' }, title: 'Your profile' },
  { path: 'sessions', loadComponent: () => import('./auth/sessions').then(m => m.Sessions), canActivate: [authenticated], data: { permission: 'sessions:read:self' }, title: 'Your sessions' },
  { path: '', component: Foundation, title: 'Career Intelligence · Foundation' },
  { path: '**', redirectTo: '' },
];
