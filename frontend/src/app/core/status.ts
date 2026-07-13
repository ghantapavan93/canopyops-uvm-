/** Presentation metadata for domain statuses. Every status carries a text
 *  label, a shape/glyph, and a tone — so meaning never rests on color alone
 *  (WCAG 1.4.1). Shared by queue, detail, map legend, and badges. */
import {
  ConstraintCategory,
  TreatmentStatus,
  WorkOrderPriority,
} from './models';

export type Tone = 'ok' | 'warn' | 'danger' | 'info' | 'neutral' | 'primary';

export interface Meta {
  label: string;
  tone: Tone;
  glyph: string; // unicode shape cue, distinguishable without color
}

export const STATUS_META: Record<TreatmentStatus, Meta> = {
  draft: { label: 'Draft', tone: 'neutral', glyph: '○' },
  scheduled: { label: 'Scheduled', tone: 'info', glyph: '◔' },
  in_progress: { label: 'In progress', tone: 'info', glyph: '◑' },
  applied: { label: 'Applied', tone: 'primary', glyph: '◕' },
  awaiting_verification: { label: 'Awaiting verification', tone: 'warn', glyph: '◇' },
  effective: { label: 'Effective', tone: 'ok', glyph: '●' },
  partially_effective: { label: 'Partially effective', tone: 'warn', glyph: '◐' },
  ineffective: { label: 'Ineffective', tone: 'danger', glyph: '✕' },
  inconclusive: { label: 'Inconclusive', tone: 'neutral', glyph: '?' },
  follow_up_planned: { label: 'Follow-up planned', tone: 'info', glyph: '↻' },
  closed: { label: 'Closed', tone: 'neutral', glyph: '▣' },
};

export const PRIORITY_META: Record<WorkOrderPriority, Meta> = {
  routine: { label: 'Routine', tone: 'neutral', glyph: '—' },
  elevated: { label: 'Elevated', tone: 'warn', glyph: '▲' },
  hazard: { label: 'Hazard', tone: 'danger', glyph: '⚠' },
};

export const CONSTRAINT_META: Record<ConstraintCategory, Meta> = {
  water_buffer: { label: 'Water buffer', tone: 'info', glyph: '≈' },
  habitat: { label: 'Habitat window', tone: 'ok', glyph: '❋' },
  steep_slope: { label: 'Steep slope', tone: 'warn', glyph: '◣' },
  no_work_zone: { label: 'No-work zone', tone: 'danger', glyph: '⊘' },
  access_restricted: { label: 'Access restricted', tone: 'warn', glyph: '⛔' },
  hftd: { label: 'Fire-threat district', tone: 'danger', glyph: '🔥' },
};

/** Tailwind classes per tone for the soft "chip" badge treatment. */
export const TONE_CHIP: Record<Tone, string> = {
  ok: 'bg-ok-soft text-ok',
  warn: 'bg-warn-soft text-warn',
  danger: 'bg-danger-soft text-danger',
  info: 'bg-info-soft text-info',
  neutral: 'bg-neutral-soft text-muted',
  primary: 'bg-primary-soft text-primary',
};

/** Map/legend fill colors per tone (hard values; MapLible can't read CSS vars). */
export const TONE_HEX: Record<Tone, { light: string; dark: string }> = {
  ok: { light: '#1f8a54', dark: '#37b57e' },
  warn: { light: '#a8720a', dark: '#d79a2b' },
  danger: { light: '#b4231f', dark: '#e5645f' },
  info: { light: '#1f5fa8', dark: '#5b9be0' },
  neutral: { light: '#5b6b62', dark: '#9db0a5' },
  primary: { light: '#1f6f4b', dark: '#37b57e' },
};
