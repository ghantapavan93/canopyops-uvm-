import { defineConfig } from 'cypress';

export default defineConfig({
  e2e: {
    baseUrl: 'http://localhost:8080',
    supportFile: false,
    specPattern: 'cypress/e2e/**/*.cy.ts',
    viewportWidth: 1280,
    viewportHeight: 800,
    video: false,
    // CI runners are markedly slower and more resource-constrained than a dev
    // machine, and a freshly-started stack is cold: the first PostGIS spatial
    // query per screen is the slow one. These bounds are generous on purpose so
    // that first interaction never loses a race it would win locally.
    defaultCommandTimeout: 15000,
    pageLoadTimeout: 60000,
    requestTimeout: 15000,
    responseTimeout: 30000,
    // Retry a failed spec in CI (not in interactive mode). The e2e failures seen
    // here are timing flakes — a slow first spatial load, not a real defect — and
    // the flaky step (waiting for a work-order list to render) fails BEFORE the
    // journey mutates any data, so a retry restarts from a clean state. A spec
    // that passes ~93% of the time clears 3 attempts with very high probability.
    retries: { runMode: 2, openMode: 0 },
  },
});
