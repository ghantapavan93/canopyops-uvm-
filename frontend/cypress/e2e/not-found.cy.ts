/// <reference types="cypress" />

/**
 * The wildcard fallback. Under Cypress the service worker is disabled, so the
 * "checking for a newer version" grace window is skipped and a genuine 404
 * renders immediately — with a working path back into the console.
 */
describe('CanopyOps not-found route', () => {
  Cypress.on('uncaught:exception', () => false);

  it('renders a real 404 for unknown routes and links home', () => {
    cy.visit('/this-route-does-not-exist');
    cy.contains('Page not found').should('exist');
    cy.contains('a', 'Go to the console').click();
    cy.location('pathname').should('include', '/console/overview');
  });
});
