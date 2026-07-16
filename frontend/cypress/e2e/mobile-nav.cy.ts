/// <reference types="cypress" />

/**
 * Mobile navigation: the module rail is desktop-only, so on a phone every module
 * must be reachable through the hamburger drawer. Regression guard for the field
 * crew — the primary mobile persona. Requires the stack on :8080.
 */
describe('Mobile navigation', () => {
  Cypress.on('uncaught:exception', () => false);

  beforeEach(() => cy.viewport('iphone-x'));

  it('opens the drawer and navigates between modules on a phone', () => {
    cy.visit('/console/execution');
    cy.contains('h1', 'Field Execution').should('exist');

    // The desktop rail is hidden; the hamburger is the only way through.
    cy.get('[aria-label="Open navigation menu"]').should('be.visible').click();
    cy.get('[role="dialog"][aria-label="Navigation menu"]').should('be.visible');

    // Navigate to another module — the drawer closes and the route changes.
    cy.get('[role="dialog"]').contains('a', 'Sync & Conflict').click();
    cy.contains('h1', 'Sync & Conflict Center').should('exist');
    cy.get('[role="dialog"][aria-label="Navigation menu"]').should('not.exist');

    // Escape closes the drawer without navigating.
    cy.get('[aria-label="Open navigation menu"]').click();
    cy.get('[role="dialog"][aria-label="Navigation menu"]').should('be.visible');
    cy.get('body').type('{esc}');
    cy.get('[role="dialog"][aria-label="Navigation menu"]').should('not.exist');
  });
});
