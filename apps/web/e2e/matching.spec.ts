import { expect, Page, test } from '@playwright/test';

// Real journeys against the isolated stack: jobs come from the fixture-site container and AI
// requests go to the test-only OpenRouter-compatible stub (no real provider or API key).

async function account(page: Page): Promise<void> {
  const email = `phase5-${crypto.randomUUID()}@example.com`;
  const password = `Phase five passphrase ${crypto.randomUUID()}`;
  await page.goto('/register');
  await page.getByLabel('Display name').fill('Phase five user');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveURL(/\/profile/);
}

async function extractedJobs(page: Page): Promise<void> {
  await page.goto('/companies/new');
  await page.getByLabel('Company name', { exact: true }).fill('Jobs Fixture Co');
  await page.getByLabel('Website URL', { exact: true }).fill('http://jobs-fixture.com/');
  await page.getByRole('button', { name: 'Save company' }).click();
  await page.getByRole('button', { name: 'Discover careers' }).click();
  await expect(page.getByRole('link', { name: 'View jobs from this source' })).toBeVisible({ timeout: 120_000 });
}

async function saveProfile(page: Page, values: Record<string, string>, weights: Record<string, string>): Promise<void> {
  for (const [label, value] of Object.entries(values)) await page.getByLabel(label, { exact: true }).fill(value);
  for (const [label, value] of Object.entries(weights)) await page.getByLabel(`${label} weight`, { exact: true }).fill(value);
  await page.getByRole('button', { name: 'Save preference profile' }).click();
}

test('ranked matches explain themselves and follow preference edits', async ({ page }) => {
  test.setTimeout(200_000);
  await account(page);
  await extractedJobs(page);

  await page.goto('/preferences/new');
  await saveProfile(page, { 'Profile name': 'Reliability', 'Preferred skills': 'Linux\nSQL',
    'Job titles': 'Site Reliability Engineer' }, { Skills: '60', 'Title and seniority': '40' });
  await page.getByRole('link', { name: 'View matches' }).click();
  await expect(page.getByText('not your chance of being hired')).toBeVisible();
  await expect(page.getByText('Matches are up to date.')).toBeVisible({ timeout: 30_000 });
  const ranked = page.getByRole('article');
  await expect(ranked.nth(0)).toContainText('Site Reliability Engineer');
  await expect(ranked.nth(0)).toContainText('70% match');
  await expect(ranked.nth(1)).toContainText('Data Analyst');
  await expect(ranked.nth(1)).toContainText('30% match');

  await page.getByRole('link', { name: 'Site Reliability Engineer' }).click();
  await expect(page.getByText('Found 1 of 2 skills in the requirements: Linux. Not found: SQL.')).toBeVisible();
  await expect(page.getByText('The job title matches Site Reliability Engineer.')).toBeVisible();

  // Advisory AI through the stub; the deterministic score is unchanged.
  await expect(page.getByText('cannot change the score')).toBeVisible();
  await page.getByRole('button', { name: 'Ask AI' }).click();
  await expect(page.getByText('Stub assessment: the posting asks for Linux and incident response.')).toBeVisible();
  await expect(page.getByText('Salary is not stated.')).toBeVisible();
  await expect(page.getByText('70% match')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Stub assessment')).toBeVisible();

  // Making Linux required rescoring: the analyst role is now excluded with a reason.
  await page.goto('/preferences');
  await page.getByRole('link', { name: 'Edit preference profile' }).click();
  await saveProfile(page, { 'Preferred skills': 'SQL', 'Required skills': 'Linux' }, {});
  await page.getByRole('link', { name: 'View matches' }).click();
  await expect(page.getByText('Matches are up to date.')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('article')).toHaveCount(1);
  await expect(page.getByRole('article').first()).toContainText('80% match');
  await page.getByRole('tab', { name: 'Excluded' }).click();
  await expect(page.getByText('A required skill is not mentioned: Linux.').first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Data Analyst' })).toBeVisible();
});

test('match detail fits a narrow viewport and other users cannot read matches', async ({ page, browser }) => {
  test.setTimeout(200_000);
  await account(page);
  await extractedJobs(page);
  await page.goto('/preferences/new');
  await saveProfile(page, { 'Profile name': 'Analyst', 'Preferred skills': 'SQL' }, { Skills: '100' });
  await page.getByRole('link', { name: 'View matches' }).click();
  await expect(page.getByText('Matches are up to date.')).toBeVisible({ timeout: 30_000 });
  await page.setViewportSize({ width: 360, height: 800 });
  await page.getByRole('link', { name: 'Data Analyst' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Data Analyst' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  const matchPath = new URL(page.url()).pathname;

  const other = await browser.newContext();
  const otherPage = await other.newPage();
  await account(otherPage);
  const response = await otherPage.request.get(`/api/v1${matchPath}`);
  expect(response.status()).toBe(404);
  await other.close();
});
