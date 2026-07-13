import { Component, ElementRef, afterNextRender, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

interface Step { n: number; t: string; d: string; glyph: string; }
interface Persona { role: string; who: string; gets: string; glyph: string; }
interface Stat { target: number; suffix: string; label: string; }

/** Cinematic scrollytelling landing. Motion is CSS-driven (compositor-based, so
 *  it runs and finishes even if the tab is backgrounded — unlike RAF/JS tweens).
 *  JS only adds flourishes (scroll-reveal class toggles, count-up, cursor glow)
 *  and NEVER gates whether content is visible: a setTimeout safety net reveals
 *  everything, and all motion honors prefers-reduced-motion. */
@Component({
  selector: 'app-landing',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './landing.component.html',
  styleUrl: './landing.component.scss',
})
export class LandingComponent {
  private host = inject(ElementRef<HTMLElement>);

  readonly tech = [
    'Angular', 'TypeScript', 'MapLibre GL', 'PostGIS', 'FastAPI', 'IndexedDB',
    'PWA offline', 'Signals', 'Jest', 'Cypress', 'WCAG AA', 'Docker',
  ];

  readonly steps: Step[] = [
    { n: 1, t: 'Plan the outcome', glyph: '◎', d: 'A manager defines a measurable vegetation outcome for a GIS treatment polygon — target condition, required evidence, constraints, and a verification window.' },
    { n: 2, t: 'Execute offline', glyph: '⛏', d: 'A field crew opens the assignment on mobile, loses connectivity, records the work, and saves locally. No signal, no data loss.' },
    { n: 3, t: 'Miss & fail', glyph: '⚠', d: 'Part of the planned area is missed, and one evidence upload fails. The record stays visibly incomplete — it cannot fake “done”.' },
    { n: 4, t: 'Recover safely', glyph: '⇅', d: 'The Sync & Conflict Center explains exactly what is local, what reached the server, and the one safe action — with zero duplicates on retry.' },
    { n: 5, t: 'Verify the result', glyph: '✓', d: 'A follow-up visit finds partial regrowth. Outcome is human-authored and evidence-linked — never an AI verdict.' },
    { n: 6, t: 'Target the re-work', glyph: '✎', d: 'The reviewer draws only the geometry that needs another pass — not a blind repeat across the whole corridor.' },
    { n: 7, t: 'Close with proof', glyph: '▣', d: 'The record closes only when plan, execution, evidence, verification, and audit history are all connected.' },
  ];

  readonly personas: Persona[] = [
    { role: 'ROW Program Manager', who: 'Owns the risk.', gets: 'A prioritized map of exceptions — what’s incomplete, overdue, or ineffective — with a clear next action in seconds.', glyph: '◧' },
    { role: 'Field Crew / Applicator', who: 'Works in the sun, in gloves.', gets: 'Large touch targets, minimal typing, and dead-honest offline state — you always know what’s saved and what still needs to sync.', glyph: '⛏' },
    { role: 'Arborist / Quality Reviewer', who: 'Signs the outcome.', gets: 'Baseline-to-outcome comparison, evidence, and audit history to justify the next action.', glyph: '✓' },
    { role: 'Compliance Reviewer', who: 'Answers to the regulator.', gets: 'Constraint overlays, record completeness, and an immutable trail built for FAC-003 and wildfire-plan scrutiny.', glyph: '⚖' },
  ];

  readonly stats: Stat[] = [
    { target: 7, suffix: '', label: 'lifecycle states, plan → verified outcome' },
    { target: 100, suffix: '%', label: 'offline drafts survive a refresh (target)' },
    { target: 0, suffix: '', label: 'duplicate records under retry storms' },
    { target: 1000, suffix: '+', label: 'synthetic map features, still responsive' },
  ];

  constructor() {
    afterNextRender(() => this.setup());
  }

  private setup(): void {
    const root = this.host.nativeElement as HTMLElement;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const revealables = Array.from(root.querySelectorAll('[data-reveal], [data-step]'));

    if (reduce || !('IntersectionObserver' in window)) {
      revealables.forEach((el) => el.classList.add('in'));
      root.querySelectorAll('[data-count]').forEach((el) => {
        el.textContent = (el as HTMLElement).dataset['count'] ?? '';
      });
      return;
    }

    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add('in');
            if ((e.target as HTMLElement).dataset['count'] !== undefined) {
              this.countUp(e.target as HTMLElement);
            }
            io.unobserve(e.target);
          }
        }
      },
      { threshold: 0.12 },
    );
    revealables.forEach((el) => io.observe(el));
    root.querySelectorAll('[data-count]').forEach((el) => io.observe(el));

    // Safety net: never leave anything hidden, even if the observer misbehaves.
    setTimeout(() => {
      revealables.forEach((el) => el.classList.add('in'));
      root.querySelectorAll('[data-count]').forEach((el) => this.countUp(el as HTMLElement));
    }, 2600);

    // Cursor-follow glow (pointer events, not RAF — always responsive).
    root.addEventListener('pointermove', (ev) => {
      const r = root.getBoundingClientRect();
      root.style.setProperty('--mx', `${((ev.clientX - r.left) / r.width) * 100}%`);
      root.style.setProperty('--my', `${((ev.clientY - r.top) / r.height) * 100}%`);
    });
  }

  private countUp(el: HTMLElement): void {
    if (el.dataset['counted']) return;
    el.dataset['counted'] = '1';
    const target = Number(el.dataset['count']);
    const steps = 28;
    let i = 0;
    // setInterval (not RAF) so it still advances when the tab is inactive.
    const timer = setInterval(() => {
      i++;
      el.textContent = String(Math.round((target * i) / steps));
      if (i >= steps) {
        el.textContent = String(target);
        clearInterval(timer);
      }
    }, 34);
  }
}
