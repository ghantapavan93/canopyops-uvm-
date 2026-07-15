/// <reference types="cypress" />

/**
 * The global command palette (Ctrl/Cmd-K): open, type-to-filter, keyboard
 * navigation, and the header trigger. Requires the full stack running
 * (docker compose up) with the frontend on :8080 proxying /api.
 */
describe('CanopyOps command palette', () => {
  // MapLibre needs WebGL; a headless GPU-less browser can throw on map routes.
  Cypress.on('uncaught:exception', () => false);

  const palette = () => cy.get('[role="dialog"][aria-label="Command palette"]');

  // The palette's document keydown listener lives in the console shell — wait
  // for the shell (its header trigger) before firing the keyboard shortcut.
  const openWithShortcut = () => {
    cy.get('header').contains('button', 'Jump to').should('be.visible');
    cy.get('body').type('{ctrl}k');
    palette().should('be.visible');
  };

  it('opens with Ctrl+K, filters, and navigates via Enter', () => {
    cy.visit('/console/overview');
    openWithShortcut();

    // Type to filter down to a single module.
    cy.get('app-command-palette input').type('terrain');
    cy.get('app-command-palette li button')
      .should('have.length', 1)
      .and('contain', '3D Terrain');

    // Enter opens it and closes the palette.
    cy.get('app-command-palette input').type('{enter}');
    cy.location('pathname').should('eq', '/console/terrain');
    palette().should('not.exist');
  });

  it('opens from the header button; Escape closes without navigating', () => {
    cy.visit('/console/overview');

    cy.get('header').contains('button', 'Jump to').click();
    palette().should('be.visible');

    cy.get('app-command-palette input').type('sync');
    cy.get('app-command-palette li button').should('contain', 'Sync & Conflict Center');

    // Escape dismisses the palette and leaves the route unchanged.
    cy.get('app-command-palette input').type('{esc}');
    palette().should('not.exist');
    cy.location('pathname').should('eq', '/console/overview');
  });

  it('opens with the shortcut and navigates to another module', () => {
    cy.visit('/console/overview');
    openWithShortcut();

    cy.get('app-command-palette input').type('geofence');
    cy.get('app-command-palette li button').should('contain', 'Geofence');
    cy.get('app-command-palette input').type('{enter}');
    cy.location('pathname').should('eq', '/console/geofence');
  });
});
