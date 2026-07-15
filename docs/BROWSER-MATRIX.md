# Browser & viewport matrix

CanopyOps uses only standard web-platform APIs plus MapLibre GL (WebGL) and the
Angular service worker — no browser-specific code paths.

## Browsers

| Browser | Min version | Notes |
|---|---|---|
| Chrome / Edge (Chromium) | last 2 majors | Primary target; the e2e suite runs headless on Electron/Chromium |
| Firefox | last 2 majors | Standard APIs + WebGL; service worker supported |
| Safari (macOS/iOS) | 16+ | WebGL + service worker supported; iOS PWA install supported |

Feature dependencies and their support floor:

| Feature | Requirement | Fallback |
|---|---|---|
| Map | WebGL (MapLibre GL) | Every map has a synchronized accessible **list equivalent** if WebGL is unavailable |
| Offline outbox | IndexedDB | App still works online-only if IndexedDB is blocked |
| PWA / app-shell cache | Service Worker | App runs as a normal web app without it |
| Layout | CSS Grid / Flexbox, custom properties | — (baseline in all supported browsers) |

## Viewports

| Class | Width | Behavior |
|---|---|---|
| Mobile (field) | 375–767 px | Mobile-first field screens, large touch targets |
| Tablet | 768–1023 px | Two-column where useful |
| Desktop (office) | ≥ 1024 px | Full multi-panel console |

Responsive via Tailwind breakpoints; the e2e suite runs at 1280×800, and field
screens are designed mobile-first.

## Verification status

- **Automated (this repo):** the full Cypress e2e + axe suite runs headless on
  Chromium/Electron and is green.
- **Manual cross-browser (Firefox/Safari real devices):** documented as the next
  step; nothing in the stack uses non-standard APIs, but a real launch would
  confirm on physical Safari/iOS and Firefox.
