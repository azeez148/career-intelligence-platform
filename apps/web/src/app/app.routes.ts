import { Routes } from '@angular/router';
import { Foundation } from './foundation';
import { authenticated, guest } from './auth/auth.guards';

export const routes: Routes = [
  { path: 'companies', loadComponent: () => import('./companies/company-list').then(m => m.CompanyList), canActivate: [authenticated], data: { permission: 'companies:read:self' }, title: 'Your companies' },
  { path: 'companies/new', loadComponent: () => import('./companies/company-editor').then(m => m.CompanyEditor), canActivate: [authenticated], data: { permission: 'companies:create:self' }, title: 'Add company' },
  { path: 'companies/:id/edit', loadComponent: () => import('./companies/company-editor').then(m => m.CompanyEditor), canActivate: [authenticated], data: { permission: 'companies:update:self' }, title: 'Edit company' },
  { path: 'scans', loadComponent: () => import('./scans/scan-list').then(m => m.ScanList), canActivate: [authenticated], data: { permission: 'scans:read:self' }, title: 'Discovery scans' },
  { path: 'scans/:id', loadComponent: () => import('./scans/scan-detail').then(m => m.ScanDetail), canActivate: [authenticated], data: { permission: 'scans:read:self' }, title: 'Discovery scan' },
  { path: 'jobs', loadComponent: () => import('./jobs/job-list').then(m => m.JobList), canActivate: [authenticated], data: { permission: 'jobs:read:self' }, title: 'Jobs' },
  { path: 'jobs/:id', loadComponent: () => import('./jobs/job-detail').then(m => m.JobDetail), canActivate: [authenticated], data: { permission: 'jobs:read:self' }, title: 'Job' },
  { path: 'preferences', loadComponent: () => import('./preferences/preference-list').then(m => m.PreferenceList), canActivate: [authenticated], data: { permission: 'preferences:read:self' }, title: 'Your preference profiles' },
  { path: 'preferences/new', loadComponent: () => import('./preferences/preference-editor').then(m => m.PreferenceEditor), canActivate: [authenticated], data: { permission: 'preferences:create:self' }, title: 'Add preference profile' },
  { path: 'preferences/:id/matches', loadComponent: () => import('./matches/match-list').then(m => m.MatchList), canActivate: [authenticated], data: { permission: 'matches:read:self' }, title: 'Matches' },
  { path: 'preferences/:id/matches/:jobId', loadComponent: () => import('./matches/match-detail').then(m => m.MatchDetail), canActivate: [authenticated], data: { permission: 'matches:read:self' }, title: 'Match' },
  { path: 'preferences/:id/edit', loadComponent: () => import('./preferences/preference-editor').then(m => m.PreferenceEditor), canActivate: [authenticated], data: { permission: 'preferences:update:self' }, title: 'Edit preference profile' },
  { path: 'login', loadComponent: () => import('./auth/credentials').then(m => m.Credentials), canActivate: [guest], title: 'Sign in' },
  { path: 'register', loadComponent: () => import('./auth/credentials').then(m => m.Credentials), canActivate: [guest], data: { registration: true }, title: 'Create account' },
  { path: 'profile', loadComponent: () => import('./auth/profile').then(m => m.Profile), canActivate: [authenticated], data: { permission: 'profile:read:self' }, title: 'Your profile' },
  { path: 'sessions', loadComponent: () => import('./auth/sessions').then(m => m.Sessions), canActivate: [authenticated], data: { permission: 'sessions:read:self' }, title: 'Your sessions' },
  { path: '', component: Foundation, title: 'Career Intelligence · Foundation' },
  { path: '**', redirectTo: '' },
];
