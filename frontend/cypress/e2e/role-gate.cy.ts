/// <reference types="cypress" />

/**
 * Role-gated workspaces must EXPLAIN themselves and offer the way forward.
 *
 * The RBAC was always correct, but a correct permission boundary that renders a
 * blank panel is indistinguishable from an unfinished feature — a reviewer read
 * Field Execution as "not built" when it was simply refusing them on purpose.
 * These guard the fix: say who it's for, and switch them in one click.
 */
describe('Role-gated workspaces', () => {
  Cypress.on('uncaught:exception', () => false);

  it('explains the gate and switches role in one click', () => {
    cy.visit('/console/execution');
    cy.contains('h1', 'Field Execution').should('exist');

    // Gated: says who it's for, not just "denied".
    cy.contains('Field Execution is for Field Crew or Program Manager').should('be.visible');

    // The data was never missing — the screen only LOOKED empty.
    cy.contains('plans ready to record').should('exist');

    // One click switches and the workspace opens.
    cy.contains('button', 'Switch to Field crew and continue').click();
    cy.contains('Field Execution is for Field Crew').should('not.exist');
    cy.get('header').contains('button', 'Field crew')
      .should('have.attr', 'aria-pressed', 'true');
  });

  it('gates verification for reviewers and names why', () => {
    cy.visit('/console/verification');
    cy.contains('Outcome Verification is for Quality Reviewer or Compliance Reviewer')
      .should('be.visible');
    // The boundary is a domain rule, not a technicality — say so.
    cy.contains('certified reviewer').should('exist');
    cy.contains('button', 'Switch to Reviewer and continue').click();
    cy.contains('Outcome Verification is for Quality Reviewer').should('not.exist');
  });

  it('gates plan creation for managers', () => {
    cy.visit('/console/plan');
    cy.contains('Treatment Plan is for Program Manager').should('be.visible');
    cy.contains('button', 'Switch to Manager and continue').click();
    cy.contains('Treatment Plan is for Program Manager').should('not.exist');
  });
});
