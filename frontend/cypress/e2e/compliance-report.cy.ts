/// <reference types="cypress" />

/**
 * The exportable compliance report: renders the program rollup, scopes to a
 * single circuit, and offers a real server-generated PDF. Requires the full
 * stack running (docker compose up) on :8080, freshly seeded.
 */
describe('CanopyOps compliance report', () => {
  Cypress.on('uncaught:exception', () => false);

  it('renders the rollup, scopes by circuit, and serves a real PDF', () => {
    // Ask the API how many plans the program has rather than hardcoding it. The
    // invariant is "the report covers every span", not "there are six" — a
    // literal here breaks every time the demo data grows (it did, when the
    // golden record landed).
    cy.request('/api/treatments?limit=500').its('body.length').then((seeded: number) => {
      cy.visit('/report');
      cy.contains('h1', 'UVM Compliance Report').should('exist');

      // program + governance sections render
      cy.contains('Program attainment').should('exist');
      cy.contains('Risk governance').should('exist');
      cy.contains(`Span detail (${seeded})`).should('exist');
      cy.get('table.tbl tbody tr').should('have.length', seeded);

      // scope to a single circuit → fewer rows, all the same circuit
      cy.get('select[data-scope="circuit"]').find('option').eq(1).then(($opt) => {
        const ckt = $opt.val() as string;
        cy.get('select[data-scope="circuit"]').select(ckt);
        cy.get('table.tbl tbody tr').should('have.length.lessThan', seeded);
        cy.get('table.tbl tbody tr').each(($tr) => cy.wrap($tr).should('contain', ckt));

        // the PDF link points at the server endpoint and honours the scope
        cy.get('a[download]').should('have.attr', 'href').and('include', `/api/reports/compliance.pdf?circuit=${ckt}`);
      });

      // narrowing the activity window keeps the PDF link in sync (adds &since=)
      cy.get('select[data-scope="window"]').select('30 days');
      cy.get('a[download]').should('have.attr', 'href').and('include', 'since=');

      // and the endpoint actually returns a real PDF
      cy.request('/api/reports/compliance.pdf').then((res) => {
        expect(res.headers['content-type']).to.eq('application/pdf');
        expect(res.body.slice(0, 5)).to.eq('%PDF-');
      });
    });
  });
});
