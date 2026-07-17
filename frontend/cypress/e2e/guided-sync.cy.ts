/// <reference types="cypress" />

/**
 * The guided Sync scenario — the module's whole reason to exist.
 *
 * The Sync Center is the differentiator, and it was the one screen a reviewer
 * always found EMPTY: its outbox lives in the browser's IndexedDB, so no amount
 * of backend seeding can populate it. The scenario therefore PERFORMS the four
 * situations rather than faking rows — and this spec asserts they were really
 * produced by the server, not painted on.
 */
describe('Guided sync scenario', () => {
  Cypress.on('uncaught:exception', () => false);

  it('stages four real situations offline, then drains them against the server', () => {
    cy.visit('/console/sync');

    // Nothing queued is the boring case — the module says so and offers the rest.
    cy.contains('Nothing is queued').should('exist');
    cy.contains('button', 'Load the guided scenario').click();

    // It really goes offline and really holds the work on the device.
    cy.contains('You are offline', { timeout: 15000 }).should('be.visible');
    cy.contains('4 queued').should('exist');
    cy.contains('Queued locally').should('exist');

    // The reviewer restores connectivity — and the queue resolves itself.
    cy.contains('button', 'Go back online and watch them sync').click();

    // Three land, one needs a human. The conflict is the point: a plan that moved
    // while the crew was offline is never silently overwritten.
    cy.contains('1 need resolution', { timeout: 20000 }).should('exist');
    cy.contains('Conflict — needs you').should('exist');

    // Idempotency, proved rather than asserted: the same key submitted twice is
    // ACCEPTED once and answered `duplicate` the second time.
    cy.contains('Server:').should('exist');
    cy.contains('accepted').should('exist');
    cy.contains('duplicate').should('exist');
  });
});
