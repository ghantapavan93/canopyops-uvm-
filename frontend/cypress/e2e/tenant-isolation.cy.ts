/// <reference types="cypress" />

/**
 * Program (tenant) isolation through the UI: switching to a different program
 * changes the whole console's data — the demo program's circuits vanish and the
 * other program's appear. Enforced server-side; requires the running stack.
 */
describe('Program (tenant) isolation', () => {
  Cypress.on('uncaught:exception', () => false);

  it('switching program swaps the data and the program badge', () => {
    cy.visit('/console/vegetation');
    cy.contains(/CKT-88/).should('exist');                 // demo program data

    // switch to the NorthGrid program (a different tenant)
    cy.get('header').contains('button', 'NorthGrid').click();
    cy.contains('NorthGrid Power').should('exist');        // program badge updates

    // re-load under the new program token → only its own data is visible
    cy.visit('/console/vegetation');
    cy.contains('NG-1201').should('exist');
    cy.contains(/CKT-88/).should('not.exist');
  });
});
