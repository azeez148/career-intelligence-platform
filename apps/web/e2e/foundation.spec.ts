import { expect, test } from '@playwright/test';

test('loads Angular and reaches the real API through the web proxy', async ({ page }) => {
  const ready = page.waitForResponse('**/api/v1/health/ready');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Career Intelligence Platform' })).toBeVisible();
  const response = await ready;
  expect(response.status()).toBe(200);
  expect(await response.json()).toEqual({ status: 'ready', checks: { database: 'ok', schema: 'ok' } });
  await expect(page.getByRole('status')).toContainText('connected and ready');
});

test('shows outage and retries against the real API', async ({ page }) => {
  await page.route('**/api/v1/health/ready', (route) => route.fulfill({
    status: 503, contentType: 'application/json', body: JSON.stringify({ status: 'not_ready' }),
  }), { times: 1 });
  await page.goto('/');
  await expect(page.getByRole('status')).toContainText('temporarily unavailable');
  await page.getByRole('button', { name: 'Check again' }).click();
  await expect(page.getByRole('status')).toContainText('connected and ready');
});
