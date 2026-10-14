import { expect, Page, test } from '@playwright/test';

// Real end-to-end journeys: the isolated Compose stack discovers and extracts jobs from the
// fixture-site container through the test-only OUTBOUND_TEST_HOSTS allowlist.

async function account(page: Page): Promise<void> {
  const email = `phase4-${crypto.randomUUID()}@example.com`;
  const password = `Phase four passphrase ${crypto.randomUUID()}`;
  await page.goto('/register');
  await page.getByLabel('Display name').fill('Phase four user');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveURL(/\/profile/);
}

async function discover(page: Page, name: string, website: string): Promise<void> {
  await page.goto('/companies/new');
  await page.getByLabel('Company name', { exact: true }).fill(name);
  await page.getByLabel('Website URL', { exact: true }).fill(website);
  await page.getByRole('button', { name: 'Save company' }).click();
  await page.getByRole('button', { name: 'Discover careers' }).click();
  await expect(page).toHaveURL(/\/scans\/[0-9a-f-]+$/);
}

test('static career site goes from discovery to job detail', async ({ page }) => {
  test.setTimeout(150_000);
  await account(page);
  await discover(page, 'Jobs Fixture Co', 'http://jobs-fixture.com/');
  // The scan page polls on its own while discovery and extraction are active.
  const viewJobs = page.getByRole('link', { name: 'View jobs from this source' });
  await expect(viewJobs).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText('Found 3 jobs.')).toBeVisible();
  await expect(page.getByText('3 new · 0 updated · 0 unchanged · 0 no longer listed')).toBeVisible();

  await viewJobs.click();
  await expect(page).toHaveURL(/\/jobs\?source_id=/);
  for (const title of ['Site Reliability Engineer', 'Data Analyst', 'Office Manager']) {
    await expect(page.getByRole('link', { name: title })).toBeVisible();
  }
  await expect(page.getByRole('heading', { level: 2 })).toHaveCount(3);

  await page.getByRole('link', { name: 'Site Reliability Engineer' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Site Reliability Engineer' })).toBeVisible();
  await expect(page.locator('.job-facts')).toContainText('Lisbon, PT');
  await expect(page.locator('.job-facts')).toContainText('Remote');
  await expect(page.locator('.job-facts')).toContainText('Full-time');
  await expect(page.locator('.job-text').first()).toContainText('Keep production healthy & observable.');
  await expect(page.locator('.job-text').nth(1)).toContainText('- Linux');
  await expect(page.getByText('Medium confidence')).toBeVisible();
  const jobUrl = page.url();

  await page.reload();
  await expect(page.getByRole('heading', { level: 1, name: 'Site Reliability Engineer' })).toBeVisible();

  // Another account cannot read this job.
  const jobId = jobUrl.split('/').pop() ?? '';
  const other = await page.context().browser()!.newContext();
  const otherPage = await other.newPage();
  await account(otherPage);
  const response = await otherPage.request.get(`/api/v1/jobs/${jobId}`);
  expect(response.status()).toBe(404);
  await otherPage.goto('/jobs');
  await expect(otherPage.getByText('No jobs match these filters yet.')).toBeVisible();
  await other.close();
});

test('script-rendered career site is extracted by the browser worker', async ({ page }) => {
  test.setTimeout(180_000);
  await account(page);
  await discover(page, 'SPA Fixture Co', 'http://spa-fixture.com/');
  await expect(page.getByText('Rendered page (browser) · low confidence')).toBeVisible({ timeout: 150_000 });
  await expect(page.getByText('Found 3 jobs.')).toBeVisible();
  await page.getByRole('link', { name: 'View jobs from this source' }).click();
  for (const title of ['Frontend Engineer', 'UX Researcher', 'Support Specialist']) {
    await expect(page.getByRole('link', { name: title })).toBeVisible();
  }
  await page.getByRole('link', { name: 'UX Researcher' }).click();
  await expect(page.getByText('Low confidence: inferred from page layout')).toBeVisible();
  await expect(page.getByText('Inferred from page layout: title, description')).toBeVisible();
});

test('job explorer filters and fits a narrow viewport', async ({ page }) => {
  test.setTimeout(150_000);
  await account(page);
  await discover(page, 'Jobs Fixture Co', 'http://jobs-fixture.com/');
  await expect(page.getByRole('link', { name: 'View jobs from this source' })).toBeVisible({ timeout: 120_000 });

  await page.setViewportSize({ width: 360, height: 800 });
  await page.getByRole('link', { name: 'Jobs', exact: true }).click();
  await page.getByLabel('Work mode').selectOption({ label: 'Remote' });
  await page.getByRole('button', { name: 'Apply filters' }).click();
  await expect(page.getByRole('link', { name: 'Site Reliability Engineer' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Data Analyst' })).toHaveCount(0);
  await page.getByLabel('Search title or department').fill('analyst');
  await page.getByLabel('Work mode').selectOption({ label: 'Any work mode' });
  await page.getByRole('button', { name: 'Apply filters' }).click();
  await expect(page.getByRole('link', { name: 'Data Analyst' })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
