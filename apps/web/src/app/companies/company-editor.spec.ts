import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { CompanyEditor } from './company-editor';
import { CompanyService } from './company.service';

describe('company editor', () => {
  const save = vi.fn();
  const get = vi.fn();
  beforeEach(() => {
    save.mockReset(); get.mockReset();
    TestBed.configureTestingModule({ imports: [CompanyEditor], providers: [provideRouter([]),
      { provide: CompanyService, useValue: { save, get } },
      { provide: ActivatedRoute, useValue: { snapshot: { paramMap: { get: () => null } } } },
    ] });
  });
  it('requires identity without submitting an empty record', async () => {
    const editor = TestBed.createComponent(CompanyEditor).componentInstance;
    await editor.save();
    expect(save).not.toHaveBeenCalled();
    expect(editor.error()).toContain('Enter a name or URL');
  });
  it('preserves unsaved fields on a duplicate or network failure', async () => {
    save.mockRejectedValue(new HttpErrorResponse({ status: 409, error: { error: { code: 'company_duplicate' } } }));
    const editor = TestBed.createComponent(CompanyEditor).componentInstance;
    editor.form.setValue({ name: 'My company', website_url: '', careers_url: 'https://jobs.example.com/' });
    await editor.save();
    expect(editor.error()).toContain('already saved');
    expect(editor.form.controls.careers_url.value).toBe('https://jobs.example.com/');
    expect(editor.busy()).toBe(false);
    expect(save).toHaveBeenCalledWith({ name: 'My company', website_url: null, careers_url: 'https://jobs.example.com/' }, null);
  });
});
