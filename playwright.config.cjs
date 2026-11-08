const { defineConfig } = require('@playwright/test');
const port = Number(process.env.GIVELIFE_TEST_PORT || 3011);
module.exports = defineConfig({
  testDir: 'tests/e2e',
  testIgnore: 'group_finder.spec.cjs',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30000,
  use: { baseURL: `http://127.0.0.1:${port}`, headless: true, trace: 'retain-on-failure' },
  webServer: {
    command: `python tests/preview_fake.py --donors --test-api --fake-ai --port ${port}`,
    url: `http://127.0.0.1:${port}/health`,
    reuseExistingServer: false,
    timeout: 30000,
  },
  reporter: [['list'], ['html', { open: 'never' }]],
});
