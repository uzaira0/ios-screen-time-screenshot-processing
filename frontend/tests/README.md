# Playwright Test Suite

Comprehensive end-to-end, visual regression, accessibility, and API integration tests for the Screenshot Annotator frontend application.

## Overview

This test suite uses Playwright to verify that the frontend correctly integrates with the backend API, handles user interactions properly, and provides a working annotation workflow for research teams.

## Test Structure

```
tests/
├── auth.setup.ts              # Authentication setup for all tests
├── fixtures/
│   ├── auth.ts                # Authentication fixtures (user & admin pages)
│   └── test-data.ts           # Mock data for tests
├── utils/
│   └── helpers.ts             # Test helper functions
├── pages/                     # Page Object Models
│   ├── HomePage.ts
│   ├── AnnotationPage.ts
│   ├── AdminPage.ts
│   └── LoginPage.ts
├── e2e/                       # End-to-end tests
│   ├── home.spec.ts
│   ├── annotation.spec.ts
│   ├── admin.spec.ts
│   ├── auth.spec.ts
│   ├── export.spec.ts
│   └── complete-workflow.spec.ts
├── visual/                    # Visual regression tests
│   └── visual.spec.ts
├── accessibility/             # Accessibility tests
│   └── accessibility.spec.ts
└── api/                       # API integration tests
    └── api.spec.ts
```

## Installation

```bash
npm install
npx playwright install
```

## Running Tests

### All Tests
```bash
npm run test:e2e
```

### Specific Test Suite
```bash
# Homepage tests
npx playwright test tests/e2e/home.spec.ts

# Annotation tests
npx playwright test tests/e2e/annotation.spec.ts

# Admin tests
npx playwright test tests/e2e/admin.spec.ts

# API tests
npx playwright test tests/api/api.spec.ts

# Visual regression tests
npx playwright test tests/visual/visual.spec.ts

# Accessibility tests
npx playwright test tests/accessibility/accessibility.spec.ts
```

### Interactive Mode
```bash
npm run test:e2e:ui
```

### Headed Mode (See browser)
```bash
npm run test:e2e:headed
```

### Debug Mode
```bash
npm run test:e2e:debug
```

## Test Configuration

### Base URL
Set the base URL via environment variable:
```bash
PLAYWRIGHT_BASE_URL=http://localhost:3002 npm run test:e2e
```

### Browser Selection
Run tests on specific browsers:
```bash
npx playwright test --project=chromium
npx playwright test --project=firefox
npx playwright test --project=webkit
```

### Mobile Testing
```bash
npx playwright test --project="Mobile Chrome"
npx playwright test --project="Mobile Safari"
```

## Authentication

Tests use a setup script (`auth.setup.ts`) to create authenticated browser contexts:

- **User context**: `playwright/.auth/user.json`
- **Admin context**: `playwright/.auth/admin.json`

These are automatically used by tests that require authentication.

## Page Object Models

Page Object Models (POMs) encapsulate page interactions for better test maintainability:

### HomePage
```typescript
const homePage = new HomePage(page);
await homePage.goto();
await homePage.selectGroup('study-2024');
```

### AnnotationPage
```typescript
const annotationPage = new AnnotationPage(page);
await annotationPage.goto();
await annotationPage.setHourlyValue(0, 30);
await annotationPage.verifyScreenshot();
```

### AdminPage
```typescript
const adminPage = new AdminPage(page);
await adminPage.goto();
await adminPage.updateUserRole('user1', 'admin');
```

## Test Data

Mock data fixtures are available in `tests/fixtures/test-data.ts`:

```typescript
import { mockScreenshot, mockGroup, mockUser } from '../fixtures/test-data';
```

## Helper Functions

Common test helpers in `tests/utils/helpers.ts`:

```typescript
import { login, waitForToast, mockAPIEndpoint } from '../utils/helpers';
```

## Visual Regression Tests

Visual tests compare screenshots against baselines:

```typescript
await expect(page).toHaveScreenshot('homepage.png');
```

Update baselines:
```bash
npx playwright test --update-snapshots
```

## Accessibility Tests

Uses `@axe-core/playwright` for accessibility scanning:

```typescript
import AxeBuilder from '@axe-core/playwright';

const accessibilityScanResults = await new AxeBuilder({ page }).analyze();
expect(accessibilityScanResults.violations).toEqual([]);
```

## API Integration Tests

Tests the backend API directly using Playwright's request context:

```typescript
const response = await request.get(`${API_URL}/screenshots/next`, {
  headers: { 'X-Username': 'testuser' },
});
expect(response.ok()).toBeTruthy();
```

## Test Reports

### HTML Report
```bash
npm run test:e2e:report
```

### CI Reports
In CI, tests generate JSON reports in `test-results.json`.

## Debugging

### Trace Viewer
View traces for failed tests:
```bash
npx playwright show-trace trace.zip
```

### Screenshots
Screenshots are automatically captured on test failure in `test-results/`.

### Videos
Videos are recorded for failed tests.

## Best Practices

1. **Use locators, not selectors**: Prefer `page.getByRole()`, `page.getByLabel()`, `page.getByTestId()`
2. **Auto-waiting**: Playwright waits automatically - avoid explicit waits
3. **Test isolation**: Each test should be independent
4. **Use POMs**: Keep test code DRY with Page Object Models
5. **Mock API responses**: Use `mockAPIEndpoint()` for predictable tests
6. **Accessibility**: Include accessibility checks in all UI tests

## Known Issues

- Canvas-based grid selector requires manual testing
- Some visual tests may need baseline updates across browsers
- WebSocket tests not yet implemented

## Contributing

When adding new tests:

1. Add test data to `fixtures/test-data.ts`
2. Add page interactions to appropriate POM
3. Use existing helpers when possible
4. Include both happy path and error cases
5. Add accessibility checks for new UI features

## CI/CD Integration

Tests run on GitHub Actions (or your CI system) with:
- Parallel execution across browsers
- Retry on failure (2 retries)
- JSON reports for analysis
- Screenshot/video artifacts on failure
