import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const require = createRequire(new URL('../../frontend/package.json', import.meta.url))
const { defineConfig, devices } = require('@playwright/test')

export default defineConfig({
  testDir: '.',
  outputDir: '../../frontend/test-results',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI
    ? [['github'], ['junit', { outputFile: fileURLToPath(new URL('../../frontend/test-reports/browser.xml', import.meta.url)) }]]
    : 'list',
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
    ...(process.env.PLAYWRIGHT_CHROMIUM_PATH
      ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } }
      : {}),
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 4173 --strictPort',
    cwd: fileURLToPath(new URL('../../frontend', import.meta.url)),
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
})
