/// <reference types="cypress" />

/**
 * The OData $batch panel on the Integration page: bundles several reads into a
 * single POST and renders each sub-response with its echoed id + status. Proves
 * the Angular⇄SAP-style batching seam end-to-end against the live stack.
 */
describe('OData $batch integration', () => {
  Cypress.on('uncaught:exception', () => false);

  it('runs several reads in one round-trip and shows per-response status', () => {
    cy.visit('/console/integration');
    cy.contains('h1', 'Integration · OData').should('exist');

    // exactly one POST to $batch is issued for the whole bundle
    cy.intercept('POST', '**/odata/$batch').as('batch');
    cy.contains('button', 'reads in 1 POST').click();
    cy.wait('@batch').its('response.statusCode').should('eq', 200);

    // the results strip reports a single round-trip and per-id 200s
    cy.contains('1 round-trip').should('exist');
    cy.contains('td', 'wbs-page').parent('tr').should('contain', '200');
    cy.contains('td', 'confirmed-cats').parent('tr').should('contain', '200');
  });
});
