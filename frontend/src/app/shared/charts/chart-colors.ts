import { Tone } from '../../core/status';

/** Tone → CSS custom property, so charts stay theme-aware (light/dark) and
 *  consistent with the app's design tokens. */
export const TONE_VAR: Record<Tone, string> = {
  ok: 'var(--c-ok)',
  warn: 'var(--c-warn)',
  danger: 'var(--c-danger)',
  info: 'var(--c-info)',
  neutral: 'var(--c-text-muted)',
  primary: 'var(--c-primary)',
};

export function toneVar(tone: string): string {
  return TONE_VAR[(tone as Tone)] ?? 'var(--c-primary)';
}

let _uid = 0;
/** Stable unique id for SVG defs (gradients, clip paths) across chart instances. */
export function chartUid(prefix: string): string {
  return `${prefix}${++_uid}`;
}
