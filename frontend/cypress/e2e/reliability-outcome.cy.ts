/// <reference types="cypress" />

/**
 * The reliability-outcome panel on the Overview: the quantitative form of
 * "closed ≠ effective" — closed work paired with per-circuit SAIDI movement,
 * driven by real record state. Requires the full stack, freshly seeded.
 */
describe('Reliability outcome panel', () => {
  Cypress.on('uncaught:exception', () => false);

  it('pairs closed work with SAIDI movement per circuit', () => {
    cy.visit('/console/overview');
    cy.contains('h2', 'Reliability outcome').should('exist');
    cy.contains('closed').should('exist');

    // the rollup + per-circuit table render with the indices UVM is judged by
    cy.contains('SAIDI').should('exist');
    cy.contains('td', /^CKT-/).should('exist');

    // at least one circuit carries an outcome verdict
    cy.contains(/closed, not effective|improving|effective|no closed work/).should('exist');
  });
});
