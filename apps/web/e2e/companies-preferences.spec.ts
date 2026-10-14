import { expect, Page, test } from '@playwright/test';

async function account(page: Page): Promise<void> {
  const email = `phase2-${crypto.randomUUID()}@example.com`;
  const password = `Phase two passphrase ${crypto.randomUUID()}`;
  await page.goto('/register');
  await page.getByLabel('Display name').fill('Phase two user');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveURL(/\/profile/);
}

test('company CRUD validates URLs, duplicates, and refresh on writes', async ({ page, context }) => {
  await account(page);
  await page.getByRole('link', { name: 'Companies', exact: true }).click();
  await expect(page.getByText('No companies saved yet.')).toBeVisible();
  await page.getByRole('link', { name: 'Add company', exact: true }).click();
  await page.getByLabel('Company name', { exact: true }).fill('Saved company');
  await page.getByLabel('Website URL', { exact: true }).fill('http://127.0.0.1/');
  await page.getByRole('button', { name: 'Save company' }).click();
  await expect(page.getByRole('alert')).toContainText('public DNS hostname');
  await page.getByLabel('Website URL', { exact: true }).fill('https://example.com/');
  await page.getByRole('button', { name: 'Save company' }).click();
  await expect(page.getByRole('heading', { name: 'Saved company' })).toBeVisible();
  await page.getByRole('link', { name: 'Edit company' }).click();
  await page.getByLabel('Careers URL').fill('https://careers.example.org/team');
  await context.clearCookies({ name: 'dev-access' });
  await page.getByRole('button', { name: 'Save company' }).click();
  await expect(page.getByText('Careers: https://careers.example.org/team')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Unverified source', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Add company', exact: true }).click();
  await page.getByLabel('Website URL', { exact: true }).fill('HTTPS://EXAMPLE.COM:443');
  await page.getByRole('button', { name: 'Save company' }).click();
  await expect(page.getByRole('alert')).toContainText('already saved');
  await page.getByRole('link', { name: 'Back to companies' }).click();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Delete company' }).click();
  await expect(page.getByText('No companies saved yet.')).toBeVisible();
});

test('multiple preference profiles persist independently and reject conflicts', async ({ page, context }) => {
  await account(page);
  await page.getByRole('link', { name: 'Preferences', exact: true }).click();
  for (const name of ['First search', 'Second search']) {
    await page.getByRole('link', { name: 'Add preference profile', exact: true }).click();
    await page.getByLabel('Profile name', { exact: true }).fill(name);
    await page.getByLabel('Preferred skills', { exact: true }).fill('C++\nC#');
    await page.getByRole('button', { name: 'Save preference profile' }).click();
    await expect(page.getByRole('alert')).toContainText('total 100');
    await page.getByLabel('Skills weight', { exact: true }).fill('100');
    await page.getByLabel('Required skills', { exact: true }).fill('C++');
    await page.getByRole('button', { name: 'Save preference profile' }).click();
    await expect(page.getByRole('alert')).toContainText('distinct');
    await page.getByLabel('Required skills', { exact: true }).fill('Python');
    await page.getByRole('button', { name: 'Save preference profile' }).click();
    await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
  }
  const first = page.locator('article').filter({ has: page.getByRole('heading', { name: 'First search', exact: true }) });
  await first.getByRole('link', { name: 'Edit preference profile' }).click();
  await page.getByLabel('Remote-work preference').selectOption('remote_only');
  await page.getByLabel('Skills weight', { exact: true }).fill('60');
  await page.getByLabel('Location and work arrangement weight').fill('40');
  await context.clearCookies({ name: 'dev-access' });
  await page.getByRole('button', { name: 'Save preference profile' }).click();
  await expect(page.getByRole('heading', { name: 'Your preference profiles' })).toBeVisible();
  await first.getByRole('link', { name: 'Edit preference profile' }).click();
  await page.reload();
  await expect(page.getByLabel('Skills weight', { exact: true })).toHaveValue('60');
  await expect(page.getByLabel('Preferred skills', { exact: true })).toHaveValue('C++\nC#');
  await page.getByRole('link', { name: 'Back to preference profiles' }).click();
  page.once('dialog', dialog => dialog.accept());
  await first.getByRole('button', { name: 'Delete preference profile' }).click();
  await expect(page.getByRole('heading', { name: 'First search', exact: true })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Second search', exact: true })).toBeVisible();
});

test('new routes isolate users, fit a narrow viewport, and respond to cross-tab logout', async ({ browser }) => {
  const first = await browser.newContext({ viewport: { width: 375, height: 812 } });
  const second = await browser.newContext();
  try {
    const a = await first.newPage(); const b = await second.newPage();
    await a.goto('/companies'); await expect(a).toHaveURL(/\/login/);
    await account(a);
    await a.goto('/companies/new');
    await a.getByLabel('Company name', { exact: true }).fill('Private saved company');
    await a.getByRole('button', { name: 'Save company' }).click();
    await a.getByRole('link', { name: 'Edit company' }).click();
    const privatePath = new URL(a.url()).pathname;
    expect(await a.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await account(b);
    await b.goto('/companies');
    await expect(b.getByText('No companies saved yet.')).toBeVisible();
    await b.goto(privatePath);
    await expect(b.getByRole('alert')).toContainText('not found');
    await a.goto('/preferences/new');
    expect(await a.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const otherTab = await first.newPage(); await otherTab.goto('/companies');
    await otherTab.getByRole('button', { name: 'Sign out', exact: true }).click();
    await expect(a).toHaveURL(/\/login/);
    await expect(otherTab).toHaveURL(/\/login/);
  } finally { await first.close(); await second.close(); }
});
