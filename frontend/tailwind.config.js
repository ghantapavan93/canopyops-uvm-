/** @type {import('tailwindcss').Config} */
// Tailwind maps onto the CSS-variable design tokens in styles.scss so every
// utility stays theme-aware (light/dark) without duplicating color values.
module.exports = {
  content: ['./src/**/*.{html,ts}'],
  darkMode: 'media',
  theme: {
    extend: {
      colors: {
        bg: 'var(--c-bg)',
        surface: 'var(--c-surface)',
        'surface-2': 'var(--c-surface-2)',
        border: 'var(--c-border)',
        ink: 'var(--c-text)',
        muted: 'var(--c-text-muted)',
        primary: {
          DEFAULT: 'var(--c-primary)',
          ink: 'var(--c-primary-ink)',
          soft: 'var(--c-primary-soft)',
        },
        ok: { DEFAULT: 'var(--c-ok)', soft: 'var(--c-ok-soft)' },
        warn: { DEFAULT: 'var(--c-warn)', soft: 'var(--c-warn-soft)' },
        danger: { DEFAULT: 'var(--c-danger)', soft: 'var(--c-danger-soft)' },
        info: { DEFAULT: 'var(--c-info)', soft: 'var(--c-info-soft)' },
        neutral: { DEFAULT: 'var(--c-neutral)', soft: 'var(--c-neutral-soft)' },
      },
      borderRadius: {
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
      },
      boxShadow: {
        card: 'var(--shadow-1)',
        pop: 'var(--shadow-2)',
      },
      fontFamily: {
        sans: 'var(--font-sans)',
        mono: 'var(--font-mono)',
      },
    },
  },
  plugins: [],
};
