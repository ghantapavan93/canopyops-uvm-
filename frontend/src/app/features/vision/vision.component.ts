import {
  Component, ElementRef, OnDestroy, afterNextRender, computed, inject, signal, viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';

interface Phase { key: 'near' | 'mid' | 'long'; horizon: string; title: string; items: string[]; }
interface Layer { icon: string; name: string; detail: string; }

/** The Future Vision — a cinematic, interactive frontend showcase of where
 *  CanopyOps goes next. Motion is CSS + canvas; content is never gated on it
 *  (scroll-reveal has a safety net) and everything honors reduced-motion. */
@Component({
  selector: 'app-vision',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './vision.component.html',
  styleUrl: './vision.component.scss',
})
export class VisionComponent implements OnDestroy {
  private host = inject(ElementRef<HTMLElement>);
  private canvas = viewChild<ElementRef<HTMLCanvasElement>>('net');

  // Long-lived resources spun up in afterNextRender — all released in ngOnDestroy
  // so leaving /vision doesn't leave a resize listener, a perpetual rAF loop, or
  // stray intervals running against a detached component.
  private rafId: number | null = null;
  private onResize: (() => void) | null = null;
  private io?: IntersectionObserver;
  private countTimers = new Set<ReturnType<typeof setInterval>>();

  // ---- interactive: roadmap phase ----
  readonly phase = signal<'near' | 'mid' | 'long'>('near');
  readonly phases: Phase[] = [
    { key: 'near', horizon: '0–1 year', title: 'Extend what exists', items: [
      'Typed ingest seam for LiDAR · multispectral/NDVI · thermal · satellite change-detection',
      'Span-level grow-in / fall-in risk scoring — ranked, forester-signed',
      'Reliability tie-out to SAIDI · SAIFI · CMI',
      'One-click NERC FAC-003 + wildfire compliance bundles (ready for the ≥100 kV expansion)',
    ] },
    { key: 'mid', horizon: '1–3 years', title: 'Close the sensing → dispatch loop', items: [
      'Multi-sensor fusion → a prioritized, planner-approved work list',
      'The AI copilot: ranks a span and explains itself in plain language — evidence shown, never a verdict',
      'Wildfire ignition-risk layer (HFTD + fuel-moisture) as human decision-support',
      'Two-way SAP S/4HANA (WBS/CATS) ⇄ GIS fabric, field stays offline-first',
    ] },
    { key: 'long', horizon: '3–5 years', title: 'The living model', items: [
      'Physics-aware digital twin: per-span sag, clearance, encroachment under wind/drought/fire',
      'Species-specific regrowth prediction → condition-based cycles, not fixed ones',
      'Always-on monitoring: IoT + autonomous BVLOS flights feed the twin continuously',
      'The loop closes: detect → rank → human-approve → dispatch → verify → re-score',
    ] },
  ];
  readonly activePhase = computed(() => this.phases.find((p) => p.key === this.phase())!);

  readonly sensing: Layer[] = [
    { icon: '🛰', name: 'Satellite', detail: 'Broad, frequent change detection — near-monthly revisits' },
    { icon: '📡', name: 'LiDAR', detail: 'Precise 3D canopy, height, and conductor-clearance geometry' },
    { icon: '🚁', name: 'Drone · BVLOS', detail: 'Long-corridor autonomous capture — visual, thermal, multispectral' },
    { icon: '🧠', name: 'Risk model', detail: 'Fuses it all into a ranked span risk — reviewed by a human' },
  ];

  // ---- interactive: the AI copilot "explain" card ----
  readonly span = {
    id: 'UVM.2026.1042', circuit: 'CKT-8843 · SPAN 14-15',
    species: 'Silver maple (fast grower)', clearanceFt: 3.2, wind: 'High exposure', outages: 2,
  };
  private readonly RATIONALE =
    'Ranked HIGH. Silver maple is a fast grower and current clearance is only 3.2 ft — below the wire-zone target. ' +
    'High wind exposure raises fall-in risk, and this span has 2 prior vegetation-caused outages. ' +
    'Recommended: schedule a directional prune this cycle. Evidence attached: LiDAR clearance profile, 2 outage tickets, species record.';
  readonly aiText = signal('');
  readonly aiState = signal<'idle' | 'typing' | 'done' | 'signed'>('idle');
  private typer: ReturnType<typeof setInterval> | null = null;

  explain(): void {
    if (this.typer) clearInterval(this.typer);
    this.aiText.set('');
    this.aiState.set('typing');
    const words = this.RATIONALE.split(' ');
    let i = 0;
    // setInterval (not RAF) so it keeps advancing even if the tab is backgrounded.
    this.typer = setInterval(() => {
      this.aiText.update((t) => t + (i ? ' ' : '') + words[i]);
      if (++i >= words.length) {
        clearInterval(this.typer!);
        this.typer = null;
        this.aiState.set('done');
      }
    }, 45);
  }
  signOff(): void { this.aiState.set('signed'); }
  resetAi(): void {
    if (this.typer) clearInterval(this.typer);
    this.aiText.set('');
    this.aiState.set('idle');
  }

  // ---- interactive: grow-in predictor ----
  readonly months = signal(6);
  private readonly CONDUCTOR_FT = 32;      // conductor height
  private readonly START_TREE_FT = 22;     // tree height at month 0
  private readonly GROWTH_FT_PER_MO = 0.42;
  readonly treeFt = computed(() => this.START_TREE_FT + this.months() * this.GROWTH_FT_PER_MO);
  readonly clearanceFt = computed(() => Math.max(0, Math.round((this.CONDUCTOR_FT - this.treeFt()) * 10) / 10));
  readonly growLevel = computed<'ok' | 'warn' | 'breach'>(() => {
    const c = this.clearanceFt();
    return c <= 2 ? 'breach' : c <= 6 ? 'warn' : 'ok';
  });
  /** Canopy top as a % height in the SVG (100 = ground, 0 = top/conductor). */
  readonly canopyY = computed(() => {
    const frac = Math.min(1, this.treeFt() / this.CONDUCTOR_FT);
    return Math.round((1 - frac) * 74 + 8); // 8..82 viewport band
  });

  constructor() {
    afterNextRender(() => { this.reveal(); this.network(); });
  }

  ngOnDestroy(): void {
    if (this.rafId != null) cancelAnimationFrame(this.rafId);
    if (this.onResize) window.removeEventListener('resize', this.onResize);
    if (this.typer) clearInterval(this.typer);
    this.io?.disconnect();
    for (const t of this.countTimers) clearInterval(t);
    this.countTimers.clear();
  }

  // ---- scroll reveal + count-up (content never hidden if JS misbehaves) ----
  private reveal(): void {
    const root = this.host.nativeElement as HTMLElement;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const els = Array.from(root.querySelectorAll('[data-reveal]'));
    if (reduce || !('IntersectionObserver' in window)) {
      els.forEach((el) => el.classList.add('in'));
      root.querySelectorAll('[data-count]').forEach((el) => (el.textContent = (el as HTMLElement).dataset['count'] ?? ''));
      return;
    }
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          e.target.classList.add('in');
          if ((e.target as HTMLElement).dataset['count'] !== undefined) this.countUp(e.target as HTMLElement);
          io.unobserve(e.target);
        }
      }
    }, { threshold: 0.14 });
    this.io = io;
    els.forEach((el) => io.observe(el));
    root.querySelectorAll('[data-count]').forEach((el) => io.observe(el));
    setTimeout(() => {
      els.forEach((el) => el.classList.add('in'));
      root.querySelectorAll('[data-count]').forEach((el) => this.countUp(el as HTMLElement));
    }, 2800);
  }
  private countUp(el: HTMLElement): void {
    if (el.dataset['counted']) return;
    el.dataset['counted'] = '1';
    const target = Number(el.dataset['count']);
    let i = 0; const steps = 26;
    const t = setInterval(() => {
      i++; el.textContent = String(Math.round((target * i) / steps));
      if (i >= steps) { el.textContent = String(target); clearInterval(t); this.countTimers.delete(t); }
    }, 32);
    this.countTimers.add(t);
  }

  // ---- decorative canvas: a drifting grid-and-canopy network ----
  private network(): void {
    const cv = this.canvas()?.nativeElement;
    if (!cv) return;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const ctx = cv.getContext('2d');
    if (!ctx) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const resize = () => { cv.width = cv.clientWidth * dpr; cv.height = cv.clientHeight * dpr; };
    resize();
    this.onResize = resize;
    window.addEventListener('resize', resize);
    const N = 46;
    const nodes = Array.from({ length: N }, (_, i) => ({
      x: ((i * 97) % 100) / 100, y: ((i * 61) % 100) / 100,
      vx: (((i * 13) % 7) - 3) * 0.00012, vy: (((i * 17) % 7) - 3) * 0.00012,
    }));
    const draw = () => {
      const w = cv.width, h = cv.height;
      ctx.clearRect(0, 0, w, h);
      for (const n of nodes) {
        n.x += n.vx; n.y += n.vy;
        if (n.x < 0 || n.x > 1) n.vx *= -1;
        if (n.y < 0 || n.y > 1) n.vy *= -1;
      }
      for (let a = 0; a < N; a++) {
        for (let b = a + 1; b < N; b++) {
          const dx = (nodes[a].x - nodes[b].x) * w, dy = (nodes[a].y - nodes[b].y) * h;
          const d = Math.hypot(dx, dy);
          if (d < w * 0.14) {
            ctx.strokeStyle = `rgba(55,226,154,${0.10 * (1 - d / (w * 0.14))})`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(nodes[a].x * w, nodes[a].y * h);
            ctx.lineTo(nodes[b].x * w, nodes[b].y * h);
            ctx.stroke();
          }
        }
      }
      for (const n of nodes) {
        ctx.fillStyle = 'rgba(34,195,230,0.5)';
        ctx.beginPath();
        ctx.arc(n.x * w, n.y * h, 1.6 * dpr, 0, Math.PI * 2);
        ctx.fill();
      }
      if (!reduce) this.rafId = requestAnimationFrame(draw);
    };
    draw();
  }
}
