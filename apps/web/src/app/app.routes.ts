import { Routes } from '@angular/router';
import { Foundation } from './foundation';

export const routes: Routes = [
  { path: '', component: Foundation, title: 'Career Intelligence · Foundation' },
  { path: '**', redirectTo: '' },
];
