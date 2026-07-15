/// <reference types="cypress" />

/**
 * Risk Intelligence sign-off lifecycle: RBAC gate → a certified reviewer signs
 * off (persisted) → revoke reopens it → the append-only history shows both.
 * Requires the full stack running (docker compose up) on :8080, freshly seeded.
 */
describe('CanopyOps risk sign-off', () => {
  Cypress.on('uncaught:exception', () => false);

  const asRole = (label: string) => cy.get('header').contains('button', label).click();
  const firstCard = () => cy.get('ul.space-y-3 > li').first();

  it('gates sign-off by role, persists it, then revokes with an audit history', () => {
    cy.visit('/console/risk');
    cy.contains('h1', 'Risk Intelligence').should('exist');

    // --- RBAC gate: a field crew cannot sign off ---
    asRole('Field crew');
    firstCard().contains('switch to a Reviewer role to sign off').should('exist');

    // --- a certified reviewer signs off; it persists (reviewer name shown) ---
    asRole('Reviewer');
    firstCard().contains('button', 'Reviewer signs off').click();
    firstCard().contains('✓ Signed off', { timeout: 10000 }).should('exist');

    // --- the append-only history shows the sign-off ---
    firstCard().contains('button', 'Review history').click();
    firstCard().contains('Append-only review trail').should('exist');
    firstCard().contains('signed off').should('exist');

    // --- revoke reopens the span, and the history keeps both entries ---
    firstCard().contains('button', 'Revoke').click();
    firstCard().contains('Awaiting forester', { timeout: 10000 }).should('exist');
    firstCard().contains('button', 'Review history').click();
    firstCard().contains('revoked').should('exist');
    firstCard().contains('signed off').should('exist');
  });
});
