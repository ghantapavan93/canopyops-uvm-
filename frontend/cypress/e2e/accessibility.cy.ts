/// <reference types="cypress" />
import 'cypress-axe';

/**
 * Automated accessibility audit (axe-core, WCAG 2.1 A/AA). Gates on serious +
 * critical violations across the primary screens. Requires the running stack.
 */
const PAGES: Array<[string, string]> = [
  ['Program Overview', '/console/overview'],
  ['Quality & Compliance', '/console/audit'],
  ['Vegetation Intelligence', '/console/vegetation'],
  ['Risk Intelligence', '/console/risk'],
  ['Compliance Report', '/report'],
];

describe('Accessibility (axe-core WCAG 2.1 A/AA)', () => {
  Cypress.on('uncaught:exception', () => false);

  for (const [name, path] of PAGES) {
    it(`no serious/critical violations — ${name}`, () => {
      cy.visit(path);
      cy.injectAxe();
      cy.wait(600); // let async widgets/maps settle
      cy.checkA11y(undefined, { includedImpacts: ['serious', 'critical'] });
    });
  }
});
