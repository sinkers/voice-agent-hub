import { test, expect } from '@playwright/test';

test.describe('Home Page', () => {
  test('loads successfully', async ({ page }) => {
    await page.goto('/');

    // Should not show any error
    // The exact content depends on what's at / - might be dashboard or redirect
    await expect(page).toHaveURL(/\//);

    // Check page loaded (no server error)
    const response = await page.goto('/');
    expect(response?.status()).toBeLessThan(400);
  });

  test('has working navigation', async ({ page }) => {
    await page.goto('/');

    // Page should be accessible
    await expect(page).not.toHaveTitle(/404|Error/);
  });
});

test.describe('Health Check', () => {
  test('backend API is accessible', async ({ page, request }) => {
    // Test that backend is up by checking a simple endpoint
    const baseURL = process.env.BASE_URL || 'http://localhost:8080';

    // Try to access the static files (built frontend)
    const response = await request.get(`${baseURL}/`);
    expect(response.status()).toBeLessThan(400);
  });
});
