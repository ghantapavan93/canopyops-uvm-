import {
  CONSTRAINT_META,
  PRIORITY_META,
  STATUS_META,
  TONE_CHIP,
  Tone,
} from './status';

const TONES: Tone[] = ['ok', 'warn', 'danger', 'info', 'neutral', 'primary'];

describe('status presentation system', () => {
  it('every treatment status has a full meta (text + shape + tone)', () => {
    for (const meta of Object.values(STATUS_META)) {
      expect(meta.label.length).toBeGreaterThan(0);
      expect(meta.glyph.length).toBeGreaterThan(0); // shape cue, not color-only
      expect(TONES).toContain(meta.tone);
    }
  });

  it('priority and constraint metas are complete', () => {
    for (const meta of [...Object.values(PRIORITY_META), ...Object.values(CONSTRAINT_META)]) {
      expect(meta.label.length).toBeGreaterThan(0);
      expect(meta.glyph.length).toBeGreaterThan(0);
    }
  });

  it('TONE_CHIP defines a class for every tone (no missing styles)', () => {
    for (const tone of TONES) {
      expect(TONE_CHIP[tone]).toMatch(/bg-.*text-/);
    }
  });
});
