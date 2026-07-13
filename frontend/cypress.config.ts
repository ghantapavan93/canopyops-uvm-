import { defineConfig } from 'cypress';

export default defineConfig({
  e2e: {
    baseUrl: 'http://localhost:8080',
    supportFile: false,
    specPattern: 'cypress/e2e/**/*.cy.ts',
    viewportWidth: 1280,
    viewportHeight: 800,
    video: false,
    // A freshly-started CI stack is cold; be forgiving on the first interactions.
    defaultCommandTimeout: 8000,
    pageLoadTimeout: 60000,
    requestTimeout: 10000,
  },
});
