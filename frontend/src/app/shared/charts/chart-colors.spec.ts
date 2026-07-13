import { chartUid, TONE_VAR, toneVar } from './chart-colors';
import { Tone } from '../../core/status';

describe('chart color + id utilities', () => {
  const tones: Tone[] = ['ok', 'warn', 'danger', 'info', 'neutral', 'primary'];

  it('maps every tone to a CSS custom property', () => {
    for (const t of tones) {
      expect(TONE_VAR[t]).toMatch(/^var\(--/);
    }
  });

  it('falls back to primary for an unknown tone', () => {
    expect(toneVar('nonsense')).toBe('var(--c-primary)');
    expect(toneVar('ok')).toBe(TONE_VAR.ok);
  });

  it('chartUid returns unique, prefixed ids', () => {
    const a = chartUid('g');
    const b = chartUid('g');
    expect(a).not.toBe(b);
    expect(a.startsWith('g')).toBe(true);
  });
});
