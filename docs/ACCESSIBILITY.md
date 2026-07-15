# Accessibility

CanopyOps targets **WCAG 2.1 AA**. Accessibility is enforced two ways: a
hand-built practice (semantics, keyboard, non-color status, reduced motion) and
an **automated axe-core gate** in CI.

## Automated audit (axe-core)

`frontend/cypress/e2e/accessibility.cy.ts` injects **axe-core 4.10** into the
live app and runs `checkA11y` on the primary screens, failing the build on any
**serious or critical** violation:

| Screen | Route | Result |
|---|---|---|
| Program Overview | `/console/overview` | ✅ 0 serious/critical |
| Quality & Compliance | `/console/audit` | ✅ 0 serious/critical |
| Vegetation Intelligence | `/console/vegetation` | ✅ 0 serious/critical |
| Risk Intelligence | `/console/risk` | ✅ 0 serious/critical |
| Compliance Report | `/report` | ✅ 0 serious/critical |

Run it:

```
npx cypress run --spec cypress/e2e/accessibility.cy.ts   # against the running stack
```

The audit runs in the harness's default **dark** color scheme; the same tokens
were verified to pass in light mode.

## What the first run found — and the fix

The initial audit surfaced **`color-contrast` (serious)** on small (10–11px)
status text: the semantic `ok / warn / danger / info` foregrounds were too dark
against their `-soft` backgrounds (ratios 2.4–4.1 vs. the 4.5 requirement),
worst in dark mode. Two systemic fixes (no per-component patching):

- **Design tokens** (`styles.scss`): darkened the light-mode status foregrounds
  and added **brighter dark-mode overrides** (`--c-ok/warn/danger/info`) so every
  status-on-soft pairing clears 4.5:1 in both themes.
- **Component helpers** (`scoreColor`, `tierColor`, `levelColor`, `effColor`,
  `completeColor`) returned hard-coded hexes that never adapted to dark mode —
  repointed at the `var(--c-*)` tokens; the report's light-only print SCSS got
  darker muted/warn/ok values directly.

Re-audit: **0 serious/critical across all five screens.**

## Non-automated practice (also verified)

- **Status never by color alone** — every status carries text + a shape glyph +
  color (WCAG 1.4.1).
- **Keyboard + focus** — interactive elements are real `<button>`/`<a>` with a
  visible focus ring; the map has a synchronized accessible list equivalent.
- **Semantics** — landmarks, `aria-pressed`/`aria-current`, labelled controls,
  live status regions.
- **Reduced motion** — all animation is disabled under
  `prefers-reduced-motion`.

## Known limitations

- The audit gates 5 primary screens, not every route; extending coverage to all
  routes is a follow-up.
- axe catches ~a third to half of WCAG issues; it is not a substitute for manual
  screen-reader testing, which is the next step before any real launch.
