/// <reference types="cypress" />

/**
 * The exportable compliance report: renders the program rollup, scopes to a
 * single circuit, and offers a real server-generated PDF. Requires the full
 * stack running (docker compose up) on :8080, freshly seeded.
 */
describe('CanopyOps compliance report', () => {
  Cypress.on('uncaught:exception', () => false);

  it('renders the rollup, scopes by circuit, and serves a real PDF', () => {
    cy.visit('/report');
    cy.contains('h1', 'UVM Compliance Report').should('exist');

    // program + governance sections render
    cy.contains('Program attainment').should('exist');
    cy.contains('Risk governance').should('exist');
    cy.contains('Span detail (6)').should('exist');
    cy.get('table.tbl tbody tr').should('have.length', 6);

    // scope to a single circuit → fewer rows, all the same circuit
    cy.get('.scope select').select('CKT-8842');
    cy.get('table.tbl tbody tr').should('have.length.lessThan', 6);
    cy.get('table.tbl tbody tr').each(($tr) => cy.wrap($tr).should('contain', 'CKT-8842'));

    // the PDF link points at the server endpoint and honours the scope
    cy.get('a[download]').should('have.attr', 'href').and('include', '/api/reports/compliance.pdf?circuit=CKT-8842');

    // and the endpoint actually returns a real PDF
    cy.request('/api/reports/compliance.pdf').then((res) => {
      expect(res.headers['content-type']).to.eq('application/pdf');
      expect(res.body.slice(0, 5)).to.eq('%PDF-');
    });
  });
});
