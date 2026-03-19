# Frontend E2E & Integration Testing Proposal

## Overview

This document proposes a comprehensive testing strategy for the Voice Agent Hub frontend to enable user-like integration testing beyond the current backend-only test suite.

## Current State

✅ **Backend Testing** (Implemented)
- Unit tests for API endpoints
- Integration tests for device auth flow
- Database operations testing
- 9 passing tests with pytest

❌ **Frontend Testing** (Missing)
- No component tests
- No E2E user flow tests
- No UI interaction tests
- LiveKit integration untested

---

## Proposed Testing Strategy

### 1. End-to-End Testing with Playwright

**Why Playwright?**
- Modern, fast, and reliable
- Built-in test recorder for easy test creation
- Cross-browser testing (Chromium, Firefox, WebKit)
- Excellent debugging tools and screenshots/videos on failure
- Native support for modern web features (WebRTC, WebSockets)
- Better than Cypress for LiveKit/WebRTC testing

**Test Coverage:**

#### **Device Authorization Flow** (`/auth/verify`)
```typescript
test('complete device authorization flow', async ({ page }) => {
  // 1. Visit verify page with device code
  await page.goto('/auth/verify?code=abc123...');

  // 2. Verify device code is displayed
  await expect(page.locator('.code')).toContainText('abc123');

  // 3. Fill in user details
  await page.fill('input[type="text"]', 'Test User');
  await page.fill('input[type="email"]', 'test@example.com');

  // 4. Submit form
  await page.click('button[type="submit"]');

  // 5. Verify waiting state
  await expect(page.locator('.waiting')).toBeVisible();

  // 6. Mock backend to approve (via API intercept)
  // ... polling should eventually show success

  // 7. Verify success message
  await expect(page.getByText('Agent connected')).toBeVisible();
});

test('handles expired device code', async ({ page }) => {
  await page.goto('/auth/verify?code=expired123');
  await page.fill('input[type="text"]', 'Test User');
  await page.fill('input[type="email"]', 'test@example.com');
  await page.click('button[type="submit"]');

  await expect(page.locator('.error')).toContainText('expired');
});

test('validates email format', async ({ page }) => {
  await page.goto('/auth/verify?code=abc123');
  await page.fill('input[type="text"]', 'Test User');
  await page.fill('input[type="email"]', 'invalid-email');

  // HTML5 validation should prevent submission
  await page.click('button[type="submit"]');
  const validationMessage = await page.locator('input[type="email"]').evaluate(
    (el: HTMLInputElement) => el.validationMessage
  );
  expect(validationMessage).toBeTruthy();
});
```

#### **Voice Call Flow** (`/call`)
```typescript
test('connects to voice call successfully', async ({ page, context }) => {
  // Grant microphone permissions
  await context.grantPermissions(['microphone']);

  // Mock LiveKit connection
  await page.route('**/connect', route => {
    route.fulfill({
      json: {
        token: 'mock-livekit-token',
        url: 'wss://mock.livekit.cloud',
        room_name: 'call-123',
        agent: 'Test Agent'
      }
    });
  });

  await page.goto('/call?agent_id=agent-123');

  // Verify connecting state
  await expect(page.getByText('Connecting')).toBeVisible();

  // Should transition to connected state
  await expect(page.getByText('Test Agent')).toBeVisible({ timeout: 10000 });

  // Verify agent state badge
  const badge = page.locator('[style*="listening"]');
  await expect(badge).toBeVisible();
});

test('displays error for invalid agent_id', async ({ page }) => {
  await page.route('**/connect', route => {
    route.fulfill({
      status: 404,
      json: { detail: 'Agent not found' }
    });
  });

  await page.goto('/call?agent_id=invalid');

  await expect(page.locator('.error')).toContainText('Agent not found');
});

test('handles microphone permission denial', async ({ page, context }) => {
  // Deny microphone permissions
  await context.grantPermissions([]);

  await page.goto('/call?agent_id=agent-123');

  // Should show some indication of mic permission issue
  // (depends on implementation - may need to add error handling)
});

test('shows correct agent states', async ({ page }) => {
  // ... mock agent state transitions
  // listening -> thinking -> speaking

  await expect(page.getByText('Listening')).toBeVisible();
  // trigger state change
  await expect(page.getByText('Thinking')).toBeVisible();
  await expect(page.getByText('Speaking')).toBeVisible();
});
```

#### **Cross-Flow Integration Tests**
```typescript
test('complete user journey: device auth to call', async ({ page, context }) => {
  // 1. Agent registers and gets call URL
  // 2. User approves device code
  // 3. Agent collects token
  // 4. User initiates call
  // 5. Verify call connection

  // This tests the full integration from device authorization to successful call connection,
  // ensuring data flow and state transitions across pages, API endpoints, and LiveKit room setup
});
```

---

### 2. Component Testing with React Testing Library

**Why React Testing Library?**
- Tests components from user perspective
- Encouraged by React team
- Better than Enzyme (deprecated)
- Integrates well with Vitest

**Test Coverage:**

```typescript
// tests/components/AgentUI.test.tsx
describe('AgentUI', () => {
  it('displays agent name', () => {
    render(<AgentUI agentName="Test Agent" state="idle" onStateChange={vi.fn()} />);
    expect(screen.getByText('Test Agent')).toBeInTheDocument();
  });

  it('shows correct state colors', () => {
    const { rerender } = render(
      <AgentUI agentName="Agent" state="listening" onStateChange={vi.fn()} />
    );

    const badge = screen.getByText('Listening').closest('div');
    expect(badge).toHaveStyle({ background: '#22c55e' });

    rerender(<AgentUI agentName="Agent" state="speaking" onStateChange={vi.fn()} />);
    expect(screen.getByText('Speaking').closest('div')).toHaveStyle({
      background: '#a855f7'
    });
  });

  it('calls onStateChange when VA state changes', () => {
    const mockOnStateChange = vi.fn();
    // ... mock useVoiceAssistant hook
    // ... verify callback is called with correct state
  });
});

// tests/components/VerifyForm.test.tsx
describe('VerifyForm', () => {
  it('submits form with valid data', async () => {
    const user = userEvent.setup();
    render(<Verify />);

    await user.type(screen.getByPlaceholderText('Your name'), 'John Doe');
    await user.type(screen.getByPlaceholderText('Email address'), 'john@example.com');
    await user.click(screen.getByText('Approve Connection'));

    // Verify API was called
    expect(mockFetch).toHaveBeenCalledWith('/auth/verify', {
      method: 'POST',
      body: JSON.stringify({
        code: 'abc123',
        name: 'John Doe',
        email: 'john@example.com'
      })
    });
  });

  it('displays loading state during submission', async () => {
    const user = userEvent.setup();
    render(<Verify />);

    await user.click(screen.getByText('Approve Connection'));
    expect(screen.getByText('Approving…')).toBeInTheDocument();
  });
});
```

---

### 3. API Mocking with MSW (Mock Service Worker)

**Why MSW?**
- Intercepts network requests at the network level
- Works in both tests and development
- Consistent mocking between E2E and component tests
- Realistic request/response handling

```typescript
// tests/mocks/handlers.ts
import { http, HttpResponse } from 'msw';

export const handlers = [
  // Device auth endpoints
  http.post('/auth/verify', async ({ request }) => {
    const body = await request.json();
    if (body.code === 'expired123') {
      return HttpResponse.json(
        { detail: 'Device code expired' },
        { status: 400 }
      );
    }
    return HttpResponse.json({ ok: true });
  }),

  http.get('/auth/device/token', ({ request }) => {
    const url = new URL(request.url);
    const code = url.searchParams.get('code');

    if (code === 'pending') {
      return HttpResponse.json({ status: 'pending' });
    }
    return HttpResponse.json({ token: 'mock-session-token' });
  }),

  // Call endpoints
  http.post('/connect', async ({ request }) => {
    const body = await request.json();
    if (body.agent_id === 'invalid') {
      return HttpResponse.json(
        { detail: 'Agent not found' },
        { status: 404 }
      );
    }
    return HttpResponse.json({
      token: 'mock-livekit-token',
      url: 'wss://mock.livekit.cloud',
      room_name: 'call-123',
      agent: 'Test Agent'
    });
  }),
];

// tests/mocks/server.ts
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);

// Setup/teardown in test setup file
beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

---

### 4. Visual Regression Testing (Optional)

**Why Visual Testing?**
- Catch unintended UI changes
- Verify responsive design
- Cross-browser visual consistency

**Tools:**
- Playwright's built-in screenshot comparison
- Percy (if budget allows)
- Chromatic (if using Storybook)

```typescript
test('verify page visual appearance', async ({ page }) => {
  await page.goto('/auth/verify?code=abc123');
  await expect(page).toHaveScreenshot('verify-page.png');
});
```

---

## Implementation Plan

### Phase 1: Setup (Week 1)
- [ ] Install Playwright: `npm install -D @playwright/test`
- [ ] Install React Testing Library: `npm install -D @testing-library/react @testing-library/user-event @testing-library/jest-dom`
- [ ] Install Vitest: `npm install -D vitest`
- [ ] Install MSW: `npm install -D msw`
- [ ] Configure Playwright (`playwright.config.ts`)
- [ ] Configure Vitest (`vitest.config.ts`)
- [ ] Set up MSW handlers

### Phase 2: Component Tests (Week 1-2)
- [ ] Write tests for AgentUI component
- [ ] Write tests for Verify page components
- [ ] Write tests for Call page components
- [ ] Mock LiveKit hooks

### Phase 3: E2E Tests (Week 2-3)
- [ ] Device auth flow tests
- [ ] Call connection tests
- [ ] Error handling tests
- [ ] Edge case tests (expired codes, invalid agents, etc.)

### Phase 4: CI Integration (Week 3)
- [ ] Add test scripts to package.json
- [ ] Update GitHub Actions workflow
- [ ] Add test reports
- [ ] Configure test artifacts (screenshots, videos)

### Phase 5: Documentation (Week 3)
- [ ] Update AGENTS.md with testing instructions
- [ ] Create test writing guidelines
- [ ] Document mock patterns

---

## Recommended File Structure

```
frontend/
├── src/
│   ├── pages/
│   │   ├── Call.tsx
│   │   └── Verify.tsx
│   └── ...
├── tests/
│   ├── e2e/                        # Playwright E2E tests
│   │   ├── device-auth.spec.ts
│   │   ├── voice-call.spec.ts
│   │   └── integration.spec.ts
│   ├── components/                 # React Testing Library tests
│   │   ├── AgentUI.test.tsx
│   │   ├── Call.test.tsx
│   │   └── Verify.test.tsx
│   ├── mocks/                      # MSW mocks
│   │   ├── handlers.ts
│   │   └── server.ts
│   ├── fixtures/                   # Test data
│   │   └── mockData.ts
│   └── setup.ts                    # Global test setup
├── playwright.config.ts
├── vitest.config.ts
└── package.json
```

---

## Sample GitHub Actions Workflow

**Note:** Component tests with React Testing Library are proposed for future implementation. Currently only E2E tests are implemented.

```yaml
# .github/workflows/ci.yml (E2E tests section - IMPLEMENTED)
# Note: Current implementation runs on master only to save CI minutes.
# For stricter quality gates, consider running on PRs as well.
  frontend-e2e:
    runs-on: ubuntu-latest
    # Recommended: Run on PRs for earlier feedback
    # if: github.ref == 'refs/heads/master'  # Current: master only
    needs: [frontend-build]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install dependencies
        working-directory: frontend
        run: npm ci

      - name: Install Playwright browsers
        working-directory: frontend
        run: npx playwright install --with-deps chromium

      - name: Run E2E tests against production
        working-directory: frontend
        env:
          # Best practice: Use secrets for environment URLs
          BASE_URL: ${{ secrets.BASE_URL || 'https://voice-agent-hub.fly.dev' }}
        run: npm run test:e2e

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: frontend/playwright-report/
          retention-days: 7

  # Future: Component tests with Vitest + React Testing Library
  # component-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install dependencies
        working-directory: frontend
        run: npm ci

      - name: Install Playwright browsers
        working-directory: frontend
        run: npx playwright install --with-deps

      - name: Run E2E tests
        working-directory: frontend
        run: npm run test:e2e

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: frontend/playwright-report/
```

---

## Key Testing Scenarios

### Critical Paths to Test

1. **Device Authorization**
   - ✅ Valid code approval
   - ✅ Expired code rejection
   - ✅ Invalid code rejection
   - ✅ Email validation
   - ✅ Polling until agent connects
   - ✅ Timeout handling

2. **Voice Call**
   - ✅ Successful connection
   - ✅ Invalid agent_id handling
   - ✅ Microphone permission handling
   - ✅ Agent state transitions
   - ✅ Disconnect handling
   - ✅ Reconnection scenarios

3. **Error Handling**
   - ✅ Network failures
   - ✅ API errors (4xx, 5xx)
   - ✅ LiveKit connection failures
   - ✅ Timeout scenarios

4. **Edge Cases**
   - ✅ Missing query parameters
   - ✅ Malformed data
   - ✅ Concurrent requests
   - ✅ Browser compatibility

---

## Benefits

1. **Catch bugs before production**
   - UI regressions detected immediately
   - Integration issues identified early

2. **Confidence in refactoring**
   - Safe to modify code with test coverage
   - Visual regression tests catch unintended changes

3. **Better developer experience**
   - Playwright test generator speeds up test writing
   - MSW makes API mocking simple

4. **Documentation**
   - Tests serve as usage examples
   - Clear expectations for component behavior

5. **CI/CD Quality Gates**
   - Automated testing on every PR
   - Video recordings of failures for debugging

---

## Cost/Effort Estimate

**Initial Setup:** 2-3 days
**Test Development:** 1-2 weeks
**Maintenance:** ~10% of feature development time

**ROI:** High - catches bugs early, reduces manual testing time, improves code quality

---

## Next Steps

1. **Get approval** for testing approach
2. **Set up tools** (Playwright, RTL, MSW)
3. **Write first test** for device auth flow
4. **Iterate** and expand coverage
5. **Document** patterns and best practices

---

## Questions to Consider

1. Do we want visual regression testing?
2. Should we mock LiveKit or test against a real instance?
3. What's our target test coverage percentage?
4. Do we need cross-browser testing or just Chromium?
5. Should we add Storybook for component development?

---

## Resources

- [Playwright Documentation](https://playwright.dev/)
- [React Testing Library](https://testing-library.com/react)
- [MSW Documentation](https://mswjs.io/)
- [Vitest](https://vitest.dev/)
- [Testing Best Practices](https://kentcdodds.com/blog/common-mistakes-with-react-testing-library)
