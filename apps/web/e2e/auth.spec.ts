import { expect, test } from '@playwright/test';

test('registration, profile, session reload, and logout', async ({ page, context }) => {
  const email = `browser-${crypto.randomUUID()}@example.com`;
  const password = `Browser passphrase ${crypto.randomUUID()}`;
  await page.goto('/profile');
  await expect(page).toHaveURL(/\/login/);
  await page.goto('/register');
  await page.getByLabel('Display name').fill('Browser user');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page.getByRole('status')).toContainText('Account created');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your profile' })).toBeVisible();
  await page.getByLabel('Display name').fill('Updated browser user');
  await page.getByLabel('About you').fill('A safe profile biography.');
  // Exercise a mutation retried after refresh, including the rotated CSRF header.
  await context.clearCookies({ name: 'dev-access' });
  await page.getByRole('button', { name: 'Save profile' }).click();
  await expect(page.getByRole('status')).toContainText('Profile saved');
  const cookies = await context.cookies();
  expect(cookies.find(cookie => cookie.name === 'dev-access')?.httpOnly).toBe(true);
  expect(cookies.find(cookie => cookie.name === 'dev-refresh')?.httpOnly).toBe(true);
  expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
  // Remove only the access cookie to exercise actual refresh and HttpOnly rotation.
  const originalRefresh = cookies.find(cookie => cookie.name === 'dev-refresh')?.value;
  await context.clearCookies({ name: 'dev-access' });
  await page.reload();
  await expect(page.getByLabel('Display name')).toHaveValue('Updated browser user');
  expect((await context.cookies()).find(cookie => cookie.name === 'dev-refresh')?.value).not.toBe(originalRefresh);
  const secondTab = await context.newPage();
  await secondTab.goto('/profile');
  await expect(secondTab.getByRole('heading', { name: 'Your profile' })).toBeVisible();
  let refreshes = 0;
  for (const tab of [page, secondTab]) tab.on('request', request => {
    if (request.url().endsWith('/api/v1/auth/refresh')) refreshes++;
  });
  await context.clearCookies({ name: 'dev-access' });
  await Promise.all([page.reload(), secondTab.reload()]);
  await expect(page.getByLabel('Display name')).toHaveValue('Updated browser user');
  await expect(secondTab.getByLabel('Display name')).toHaveValue('Updated browser user');
  expect(refreshes).toBe(1);
  await page.getByRole('link', { name: 'Sessions', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Current session' })).toBeVisible();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page).toHaveURL(/\/login/);
  await expect(secondTab).toHaveURL(/\/login/);
  await page.goto('/profile');
  await expect(page).toHaveURL(/\/login/);
});

test('duplicate registration and incorrect login show safe errors', async ({ page }) => {
  const email = `duplicate-${crypto.randomUUID()}@example.com`;
  const password = `Browser passphrase ${crypto.randomUUID()}`;
  const register = async () => {
    await page.goto('/register');
    await page.getByLabel('Display name').fill('Duplicate user');
    await page.getByLabel('Email', { exact: true }).fill(email);
    await page.getByLabel('Password', { exact: true }).fill(password);
    await page.getByRole('button', { name: 'Create account' }).click();
  };
  await register();
  await expect(page).toHaveURL(/\/login/);
  await register();
  await expect(page.getByRole('alert')).toContainText('already registered');
  await page.goto('/login');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password + 'wrong');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('incorrect');
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue('');
});

test('separate users stay isolated and sign out everywhere revokes another browser', async ({ browser }) => {
  const first = await browser.newContext();
  const second = await browser.newContext();
  const third = await browser.newContext();
  const password = `Session passphrase ${crypto.randomUUID()}`;
  const firstEmail = `first-${crypto.randomUUID()}@example.com`;
  const secondEmail = `second-${crypto.randomUUID()}@example.com`;
  try {
    const pageA = await first.newPage();
    const pageB = await second.newPage();
    const pageC = await third.newPage();
    for (const [page, email, name] of [[pageA, firstEmail, 'First user'], [pageB, secondEmail, 'Second user']] as const) {
      await page.goto('/register');
      await page.getByLabel('Display name').fill(name);
      await page.getByLabel('Email', { exact: true }).fill(email);
      await page.getByLabel('Password', { exact: true }).fill(password);
      await page.getByRole('button', { name: 'Create account' }).click();
      await expect(page).toHaveURL(/\/login/);
    }
    for (const [page, email] of [[pageA, firstEmail], [pageB, secondEmail], [pageC, firstEmail]] as const) {
      await page.goto('/login');
      await page.getByLabel('Email', { exact: true }).fill(email);
      await page.getByLabel('Password', { exact: true }).fill(password);
      await page.getByRole('button', { name: 'Sign in', exact: true }).click();
      await expect(page.getByRole('heading', { name: 'Your profile' })).toBeVisible();
    }
    await expect(pageA.getByLabel('Display name')).toHaveValue('First user');
    await expect(pageB.getByLabel('Display name')).toHaveValue('Second user');
    await pageA.goto('/sessions');
    await expect(pageA.getByRole('heading', { name: 'Other session' })).toBeVisible();
    await pageA.getByRole('button', { name: 'Sign out everywhere' }).click();
    await expect(pageA).toHaveURL(/\/login/);
    await pageC.reload();
    await expect(pageC).toHaveURL(/\/login/);
    await pageB.reload();
    await expect(pageB.getByLabel('Display name')).toHaveValue('Second user');
    await pageB.goto('/sessions');
    await pageB.getByRole('button', { name: 'Revoke session', exact: true }).click();
    await expect(pageB).toHaveURL(/\/login/);
  } finally { await first.close(); await second.close(); await third.close(); }
});
