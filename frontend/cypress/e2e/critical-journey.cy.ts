/// <reference types="cypress" />

/**
 * The critical field-to-verification journey:
 *   plan (seeded) -> offline execution -> partial upload -> conflict recovery
 *   -> verification -> targeted follow-up -> close.
 *
 * Requires the full stack running (docker compose up) with the frontend on
 * :8080 proxying /api to the FastAPI backend, seeded with synthetic data.
 */
describe('CanopyOps critical journey', () => {
  // MapLibre needs WebGL; a headless GPU-less browser can throw. Those errors
  // are not part of this workflow, so don't let them fail the test.
  Cypress.on('uncaught:exception', () => false);

  const asRole = (label: string) =>
    cy.get('header').contains('button', label).click();

  it('records offline, recovers a conflict, verifies, and closes with proof', () => {
    // --- Field crew records an execution while offline ---
    cy.visit('/console/execution');
    asRole('Field crew');
    cy.contains('button', 'Off').click(); // simulate signal loss
    cy.contains('Offline').should('exist');

    // The work-order list is fetched after the visit + role switch, and the
    // FIRST spatial query on a cold/loaded CI runner is slow (the same latency
    // the CI job's warm-up step exists to blunt). The default 8s command timeout
    // is occasionally too tight for that first render, which is what flaked this
    // flagship journey red ~7% of runs. Every other async step in this test
    // already uses an explicit generous timeout; these first-load work-order
    // lookups were the two that were missed. Give them the same.
    cy.contains('button', 'WO-2026-1001', { timeout: 20000 }).click();
    cy.get('#cov').invoke('val', 60).trigger('input');
    cy.contains('60%').should('exist');
    cy.get('input[type=checkbox]').first().check(); // simulate a failed upload
    cy.contains('button', 'Record execution').click();
    cy.contains('Saved locally').should('exist');

    // --- Sync & Conflict Center: force a conflict, then resolve ---
    cy.contains('a', 'Open Sync Center').click(); // stays in-SPA
    cy.contains('button', 'Simulate concurrent edit').click();
    cy.contains('button', 'On').click(); // reconnect -> auto-sync
    cy.contains('Conflict', { timeout: 15000 }).should('exist');
    cy.contains('Server revision').parent().should('contain', '2');
    cy.contains('button', 'Adopt server revision').click();
    cy.contains('Synced', { timeout: 15000 }).should('exist');

    // recover the failed evidence upload — let the item re-render settle first
    cy.wait(800);
    cy.contains('button', 'photo after: failed', { timeout: 10000 })
      .should('be.visible')
      .click();
    cy.contains('complete', { timeout: 10000 }).should('exist');

    // --- Reviewer verifies the outcome and closes the record ---
    cy.visit('/console/verification');
    asRole('Reviewer');
    // Same first-load-after-role-switch pattern as WO-2026-1001 above.
    cy.contains('button', 'WO-2026-1002', { timeout: 20000 }).click();
    cy.contains('button', 'Partially effective').click();
    cy.get('textarea').type('Partial regrowth in south subsection.');
    cy.contains('button', 'Record verification').click();
    cy.contains('button', 'Plan targeted follow-up').click();
    cy.contains('button', 'Close record').click();

    // --- Proof Pack assembled with the full audit trail ---
    cy.contains('Proof Pack assembled', { timeout: 8000 }).should('exist');
    cy.contains('plan.verified').should('exist');
    cy.contains('plan.closed').should('exist');
  });
});
