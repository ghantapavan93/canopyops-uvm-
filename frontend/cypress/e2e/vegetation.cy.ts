/// <reference types="cypress" />

/**
 * Vegetation Intelligence: the hot-spotting heat layer (reactive-repeat
 * intensity over corridor spans) and the cycle-buster watchlist (fast-regrowth
 * spans ranked by days-to-conflict). Requires the full stack, freshly seeded.
 */
describe('Vegetation Intelligence', () => {
  Cypress.on('uncaught:exception', () => false);

  it('shows hot-spotting heat and a cycle-buster watchlist', () => {
    cy.visit('/console/vegetation');
    cy.contains('h1', 'Vegetation Intelligence').should('exist');

    // hot-spotting: ranked list renders and a span drives a driver breakdown
    cy.contains('h2', 'Hot-spotting heat').should('exist');
    cy.get('table').first().find('tbody tr').first().click();
    cy.contains("why it's hot").should('exist');
    cy.contains('Reactive / repeat work').should('exist');

    // cycle busters: watchlist with species + days-to-conflict + a filter
    cy.contains('h2', 'Cycle-buster watchlist').should('exist');
    cy.contains('Days to conflict').should('exist');
    cy.contains('button', /Show all species|Cycle busters only/).click();
    cy.contains('cycle buster').should('exist');
  });
});
