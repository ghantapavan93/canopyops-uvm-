/// <reference types="cypress" />

/**
 * Quality & Compliance: the independent work-plan QA audit (objective checks →
 * RBAC-gated verdict → append-only history) and the compliance evidence vault
 * (per-plan dossier mapped to NERC/TVMP/NESC frameworks). Requires the full
 * stack running on :8080, freshly seeded.
 */
describe('Quality & Compliance', () => {
  Cypress.on('uncaught:exception', () => false);

  const asRole = (label: string) => cy.get('header').contains('button', label).click();

  it('audits closed work with a verdict and shows the framework-mapped vault', () => {
    cy.visit('/console/audit');
    cy.contains('h1', 'Quality & Compliance').should('exist');
    asRole('Reviewer');

    // --- QA audit: expand a row → objective checklist → record a verdict ---
    cy.contains('h2', 'Work-plan audit (QA)').should('exist');
    cy.get('table').first().find('tbody tr').first().click();
    cy.contains('critical').should('exist');                 // the objective checklist detail
    cy.contains('button', 'conditional').click();
    cy.contains('Audit history (append-only)').should('exist');
    cy.contains('% checks').should('exist');

    // --- evidence vault: expand a dossier → framework requirements + chain ---
    cy.contains('h2', 'Compliance evidence vault').parents('section').first().within(() => {
      cy.get('button').first().click();
    });
    cy.contains('Framework requirements').should('exist');
    cy.contains('Evidence chain').should('exist');
    cy.contains('NERC FAC-003').should('exist');
  });
});
