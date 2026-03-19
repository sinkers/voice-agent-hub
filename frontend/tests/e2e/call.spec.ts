import { test, expect } from '@playwright/test';

test.describe('Voice Call Page', () => {
  test('shows error when no agent_id is provided', async ({ page }) => {
    await page.goto('/call');

    // Should show error about missing agent_id
    await expect(page.getByText(/No agent_id provided/i)).toBeVisible();
  });

  test('initiates connection when agent_id is provided', async ({ page }) => {
    // Mock the connect endpoint
    await page.route('**/connect', async (route) => {
      const request = route.request();
      const postData = request.postDataJSON();

      expect(postData.agent_id).toBe('agent123');

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          token: 'mock-livekit-token',
          url: 'wss://mock.livekit.cloud',
          room_name: 'call-abc123',
          agent: 'Test Agent',
        }),
      });
    });

    await page.goto('/call?agent_id=agent123');

    // Should show connecting state initially
    await expect(page.getByText(/Connecting/i)).toBeVisible();

    // After mock resolves, should show agent name
    // Note: LiveKitRoom component may need actual WebSocket, so this might not fully connect
    // In a real test environment, we'd mock LiveKit more thoroughly
    await expect(page.getByText('Test Agent')).toBeVisible({ timeout: 10000 });
  });

  test('handles invalid agent_id error', async ({ page }) => {
    // Mock 404 response for invalid agent
    await page.route('**/connect', async (route) => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Agent not found' }),
      });
    });

    await page.goto('/call?agent_id=invalid-agent');

    // Should show error message
    await expect(page.getByText(/Agent not found/i)).toBeVisible();
  });

  test('displays connect button when agent_id is missing', async ({ page }) => {
    await page.goto('/call');

    // Should show connect button (though it won't work without agent_id)
    const connectButton = page.getByRole('button', { name: /Connect/i });
    await expect(connectButton).toBeVisible();
  });

  test('shows agent state badge after connection', async ({ page, context }) => {
    // Grant microphone permissions
    await context.grantPermissions(['microphone']);

    // Mock the connect endpoint
    await page.route('**/connect', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          token: 'mock-token',
          url: 'wss://mock.livekit.cloud',
          room_name: 'call-test',
          agent: 'Test Agent',
        }),
      });
    });

    await page.goto('/call?agent_id=agent123');

    // Wait for agent name to appear
    await expect(page.getByText('Test Agent')).toBeVisible({ timeout: 10000 });

    // Should have some state badge (idle, connecting, listening, etc.)
    // The exact state depends on LiveKit connection, so we just check something is there
    const badge = page.locator('[style*="borderRadius"]').filter({ hasText: /Idle|Connecting|Listening|Thinking|Speaking/i });
    await expect(badge.first()).toBeVisible();
  });
});
