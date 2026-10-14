import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { PreferenceEditor } from './preference-editor';
import { PreferenceService } from './preference.service';

describe('preference editor', () => {
  const save = vi.fn();
  beforeEach(() => {
    save.mockReset();
    TestBed.configureTestingModule({ imports: [PreferenceEditor], providers: [provideRouter([]),
      { provide: PreferenceService, useValue: { save } },
      { provide: ActivatedRoute, useValue: { snapshot: { paramMap: { get: () => null } } } },
    ] });
  });
  it('starts without business defaults and blocks unallocated weights', async () => {
    const editor = TestBed.createComponent(PreferenceEditor).componentInstance;
    expect(editor.weightTotal()).toBe(0);
    editor.form.controls.name.setValue('My profile');
    editor.form.controls.required_skills.setValue('User-defined skill');
    await editor.save();
    expect(save).not.toHaveBeenCalled();
    expect(editor.error()).toContain('total 100');
  });
  it('retains criteria on rejected save and serializes the complete document', async () => {
    save.mockRejectedValue(new HttpErrorResponse({ status: 409, error: { error: { code: 'preference_duplicate' } } }));
    const editor = TestBed.createComponent(PreferenceEditor).componentInstance;
    editor.form.patchValue({ name: 'Profile', preferred_skills: 'C++\nC#', weights: { skills: 100 } });
    await editor.save();
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ name: 'Profile', criteria: expect.objectContaining({ preferred_skills: ['C++', 'C#'] }) }), null);
    expect(editor.form.controls.preferred_skills.value).toBe('C++\nC#');
    expect(editor.error()).toContain('already used');
    expect(editor.busy()).toBe(false);
  });
});
