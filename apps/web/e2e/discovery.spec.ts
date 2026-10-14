import { expect, Page, test } from '@playwright/test';

async function account(page: Page): Promise<void> {
  const email = `phase3-${crypto.randomUUID()}@example.com`;
  const password = `Phase three passphrase ${crypto.randomUUID()}`;
  await page.goto('/register');
  await page.getByLabel('Display name').fill('Phase three user');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveURL(/\/profile/);
}

test('name-only discovery requires confirmation and preserves rejected input', async ({ page }) => {
  await account(page);
  await page.goto('/companies/new');
  await page.getByLabel('Company name', { exact: true }).fill('Phase Three Candidate');
  await page.getByRole('button', { name: 'Save company' }).click();
  await page.getByRole('button', { name: 'Discover careers' }).click();
  await expect(page.getByText('Choose a suggested website')).toBeVisible();
  await expect(page.getByText('https://phasethreecandidate.com/')).toBeVisible();

  const manual = page.getByLabel('Official website URL');
  await manual.fill('http://127.0.0.1/private');
  await page.getByRole('button', { name: 'Continue with URL' }).click();
  await expect(page.getByRole('alert')).toContainText('Check field');
  await expect(manual).toHaveValue('http://127.0.0.1/private');

  await page.getByRole('button', { name: 'Use this website' }).click();
  await expect(page).toHaveURL(/\/scans\/[0-9a-f-]+$/);
  await expect(page.getByText('Selected URL: https://phasethreecandidate.com/')).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Discovery scan' })).toBeVisible();
});

test('completed source renders as text and terminal detail stops polling', async ({ page }) => {
  await account(page);
  const scanId = '00000000-0000-0000-0000-000000000099';
  let requests = 0;
  await page.route(`**/api/v1/scans/${scanId}`, async route => {
    requests += 1;
    await route.fulfill({ json: {
      id: scanId, company_id: '00000000-0000-0000-0000-000000000001', parent_scan_id: null,
      status: 'succeeded', selected_url: 'https://fixture.example/', failure_code: null,
      attempt_count: 1, created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      started_at: new Date().toISOString(), completed_at: new Date().toISOString(),
      resolved_website_url: 'https://fixture.example/', resolution_confidence: 'user_supplied',
      resolution_evidence: ['user_supplied_start'], candidates: [], sources: [{
        id: '00000000-0000-0000-0000-000000000098', url: 'https://jobs.lever.co/fixture',
        kind: 'ats', platform: 'lever', discovery_method: 'homepage_link',
        evidence: ['ats_recognized'], created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      }],
    } });
  });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`/scans/${scanId}`);
  await expect(page.getByText('Career source discovery completed.')).toBeVisible();
  const source = page.getByText('https://jobs.lever.co/fixture');
  await expect(source).toBeVisible();
  await expect(source).not.toHaveAttribute('href');
  await page.waitForTimeout(3200);
  expect(requests).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
