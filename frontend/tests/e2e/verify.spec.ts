import { test, expect } from '@playwright/test';

test.describe('Device Verification Page', () => {
  test('displays device code from URL parameter', async ({ page }) => {
    const deviceCode = 'abc123def456';
    await page.goto(`/auth/verify?code=${deviceCode}`);

    // Check page title
    await expect(page.locator('h1')).toContainText('Connect Voice Agent');

    // Check device code is displayed (first 6 chars should be visible)
    const codeElement = page.locator('[style*="2rem"]').first();
    await expect(codeElement).toBeVisible();
    await expect(codeElement).toContainText(deviceCode.substring(0, 6));
  });

  test('shows form inputs for name and email', async ({ page }) => {
    await page.goto('/auth/verify?code=test123');

    // Check form exists
    const nameInput = page.getByPlaceholder('Your name');
    const emailInput = page.getByPlaceholder('Email address');
    const submitButton = page.getByRole('button', { name: /Approve Connection/i });

    await expect(nameInput).toBeVisible();
    await expect(emailInput).toBeVisible();
    await expect(submitButton).toBeVisible();
  });

  test('requires name and email to be filled', async ({ page }) => {
    await page.goto('/auth/verify?code=test123');

    const submitButton = page.getByRole('button', { name: /Approve Connection/i });

    // Try to submit without filling fields
    await submitButton.click();

    // HTML5 validation should prevent submission
    const nameInput = page.getByPlaceholder('Your name');
    const isValid = await nameInput.evaluate((el: HTMLInputElement) => el.validity.valid);
    expect(isValid).toBe(false);
  });

  test('validates email format', async ({ page }) => {
    await page.goto('/auth/verify?code=test123');

    await page.getByPlaceholder('Your name').fill('Test User');
    await page.getByPlaceholder('Email address').fill('invalid-email');

    const emailInput = page.getByPlaceholder('Email address');
    const isValid = await emailInput.evaluate((el: HTMLInputElement) => el.validity.valid);
    expect(isValid).toBe(false);
  });

  test('can fill and submit form with valid data', async ({ page }) => {
    // Intercept the verify API call
    await page.route('**/auth/verify', async (route) => {
      const request = route.request();
      const postData = request.postDataJSON();

      // Validate the request
      expect(postData.name).toBe('Test User');
      expect(postData.email).toBe('test@example.com');
      expect(postData.code).toBe('test123');

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
    });

    // Mock the polling endpoint to return pending initially
    await page.route('**/auth/device/token?code=test123', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'pending' }),
      });
    });

    await page.goto('/auth/verify?code=test123');

    // Fill the form
    await page.getByPlaceholder('Your name').fill('Test User');
    await page.getByPlaceholder('Email address').fill('test@example.com');

    // Submit
    await page.getByRole('button', { name: /Approve Connection/i }).click();

    // Should show waiting state
    await expect(page.getByText(/Waiting for agent/i)).toBeVisible({ timeout: 5000 });
  });

  test('handles expired device code error', async ({ page }) => {
    // Mock API to return error
    await page.route('**/auth/verify', async (route) => {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Device code expired' }),
      });
    });

    await page.goto('/auth/verify?code=expired123');

    await page.getByPlaceholder('Your name').fill('Test User');
    await page.getByPlaceholder('Email address').fill('test@example.com');
    await page.getByRole('button', { name: /Approve Connection/i }).click();

    // Should show error message
    await expect(page.getByText(/expired/i)).toBeVisible();
  });
});
