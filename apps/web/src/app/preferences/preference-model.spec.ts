import { Criteria, criteriaError, entries } from './preference-model';

function valid(): Criteria {
  return { preferred_skills: ['C++', 'C#'], required_skills: ['Python'], preferred_keywords: [], excluded_keywords: [],
    job_titles: [], seniority_preferences: [], locations: [], employment_types: [], remote_policy: 'any',
    experience_min_months: null, experience_max_months: null,
    weights: { skills: 100, title: 0, location: 0, experience: 0, employment: 0, keywords: 0 } };
}

describe('preference form rules', () => {
  it('preserves punctuation and comma-bearing entries', () => {
    expect(entries(' C++\nC#\nWashington, DC\n\n')).toEqual(['C++', 'C#', 'Washington, DC']);
    expect(criteriaError(valid())).toBe('');
  });
  it('rejects duplicate and conflicting criteria', () => {
    const c = valid(); c.preferred_skills.push(' c++ ');
    expect(criteriaError(c)).toContain('duplicate');
    c.preferred_skills = ['Ｐｙｔｈｏｎ'];
    expect(criteriaError(c)).toContain('distinct');
    c.preferred_skills = ['C++']; c.excluded_keywords = ['python'];
    expect(criteriaError(c)).toContain('exclusions');
  });
  it('checks weights and requires configured factors', () => {
    const c = valid(); c.weights.skills = 99;
    expect(criteriaError(c)).toContain('total 100');
    c.weights.skills = 50; c.weights.location = 50;
    expect(criteriaError(c)).toContain('needs criteria');
    c.remote_policy = 'remote_only'; c.locations = ['User-defined region'];
    expect(criteriaError(c)).toBe('');
  });
  it('checks numeric bounds and total entry limits', () => {
    const c = valid(); c.experience_min_months = 12; c.experience_max_months = 6;
    expect(criteriaError(c)).toContain('Minimum');
    c.experience_max_months = 12.5;
    expect(criteriaError(c)).toContain('whole months');
    c.locations = Array.from({ length: 51 }, (_, i) => String(i));
    expect(criteriaError(c)).toContain('50 entries');
  });
});
