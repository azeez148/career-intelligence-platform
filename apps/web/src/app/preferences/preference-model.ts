export const listFields = [
  { key: 'preferred_skills', label: 'Preferred skills' }, { key: 'required_skills', label: 'Required skills' },
  { key: 'preferred_keywords', label: 'Preferred keywords' }, { key: 'excluded_keywords', label: 'Excluded keywords' },
  { key: 'job_titles', label: 'Job titles' }, { key: 'seniority_preferences', label: 'Seniority preferences' },
  { key: 'locations', label: 'Locations' }, { key: 'employment_types', label: 'Employment types' },
] as const;
export const weightFields = [
  { key: 'skills', label: 'Skills' }, { key: 'title', label: 'Title and seniority' },
  { key: 'location', label: 'Location and work arrangement' }, { key: 'experience', label: 'Experience' },
  { key: 'employment', label: 'Employment type' }, { key: 'keywords', label: 'Keywords' },
] as const;
export type ListKey = typeof listFields[number]['key'];
export type WeightKey = typeof weightFields[number]['key'];
export type RemotePolicy = 'any' | 'remote_only' | 'exclude_remote';
export type Criteria = Record<ListKey, string[]> & {
  remote_policy: RemotePolicy; experience_min_months: number | null; experience_max_months: number | null;
  weights: Record<WeightKey, number>;
};
export interface PreferenceInput { name: string; criteria: Criteria }
export interface PreferenceSummary { id: string; name: string; created_at: string; updated_at: string }
export interface Preference extends PreferenceSummary { criteria: Criteria }
export interface PreferencePage { items: PreferenceSummary[]; next_offset: number | null }

export function entries(value: string): string[] { return value.split(/\r?\n/).map(item => item.trim()).filter(Boolean); }
function key(value: string): string { return value.normalize('NFKC').trim().replace(/\s+/g, ' ').toLowerCase(); }

export function criteriaError(criteria: Criteria): string {
  const lists = listFields.map(field => criteria[field.key]);
  if (lists.some(values => values.length > 50 || values.some(value => !value.trim() || [...value].length > 100)) ||
    lists.reduce((count, values) => count + values.length, 0) > 200) return 'Use up to 50 entries per list, 100 characters per entry, and 200 entries in total.';
  if (lists.some(values => new Set(values.map(key)).size !== values.length)) return 'Remove duplicate list entries.';
  const overlaps = (a: string[], b: string[]) => a.some(value => new Set(b.map(key)).has(key(value)));
  if (overlaps(criteria.preferred_skills, criteria.required_skills) || overlaps(criteria.excluded_keywords,
    [...criteria.preferred_skills, ...criteria.required_skills, ...criteria.preferred_keywords, ...criteria.job_titles])) return 'Required and preferred skills must be distinct; exclusions must not conflict with desired criteria.';
  const min = criteria.experience_min_months, max = criteria.experience_max_months;
  if ([min, max].some(value => value !== null && (!Number.isInteger(value) || value < 0 || value > 1200))) return 'Experience must be whole months from 0 to 1200.';
  if (min !== null && max !== null && min > max) return 'Minimum experience cannot exceed maximum experience.';
  const weights = Object.values(criteria.weights);
  if (weights.some(value => !Number.isInteger(value) || value < 0 || value > 100) || weights.reduce((sum, value) => sum + value, 0) !== 100) return 'Weights must be whole numbers from 0 to 100 and total 100.';
  const configured: Record<WeightKey, boolean> = {
    skills: !!(criteria.preferred_skills.length || criteria.required_skills.length),
    title: !!(criteria.job_titles.length || criteria.seniority_preferences.length),
    location: !!criteria.locations.length || criteria.remote_policy !== 'any',
    experience: min !== null || max !== null, employment: !!criteria.employment_types.length,
    keywords: !!criteria.preferred_keywords.length,
  };
  return weightFields.some(field => criteria.weights[field.key] > 0 && !configured[field.key])
    ? 'Every positive weight needs criteria for that factor.' : '';
}
