/** @type {import('tailwindcss').Config} */
export default {
  // Dark command-center theme only — enforced pre-render in main.tsx.
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      colors: {
        // Surface scale — neutral graphite (no blue cast)
        surface: {
          0: 'rgb(var(--surface-0) / <alpha-value>)',
          1: 'rgb(var(--surface-1) / <alpha-value>)',
          2: 'rgb(var(--surface-2) / <alpha-value>)',
          3: 'rgb(var(--surface-3) / <alpha-value>)',
        },
        line: 'rgb(var(--line) / <alpha-value>)',
        'line-strong': 'rgb(var(--line-strong) / <alpha-value>)',
        ink: {
          DEFAULT: 'rgb(var(--ink) / <alpha-value>)',
          muted: 'rgb(var(--ink-muted) / <alpha-value>)',
          faint: 'rgb(var(--ink-faint) / <alpha-value>)',
        },
        brand: {
          DEFAULT: 'rgb(var(--brand) / <alpha-value>)',
          // Filled-control variant — deep teal, white labels pass AA.
          strong: 'rgb(var(--brand-strong) / <alpha-value>)',
          soft: 'rgb(var(--brand-soft) / <alpha-value>)',
        },
        // Severity / status semantic tokens — desaturated, dark-surface tuned.
        // Color carries meaning only; nothing glows.
        critical: '#fb7185',
        high: '#fb923c',
        medium: '#e3b341',
        low: '#7dd3fc',
        info: '#a1a1aa',
        online: '#4ade80',
        offline: '#f87171',
        degraded: '#fbbf24',
        processing: '#a1a1aa',
      },
      fontSize: {
        // Legibility pass: everything is a step larger than a classic dense
        // console so the screen stays readable at arm's length in a control
        // room, or on a duty officer's laptop.
        '2xs': ['0.8125rem', { lineHeight: '1.2rem', letterSpacing: '0.01em' }],
        xs: ['0.875rem', { lineHeight: '1.25rem' }],
        sm: ['0.9375rem', { lineHeight: '1.4rem' }],
        base: ['1rem', { lineHeight: '1.55rem' }],
        lg: ['1.125rem', { lineHeight: '1.7rem' }],
        xl: ['1.3125rem', { lineHeight: '1.85rem' }],
      },
      boxShadow: {
        // Flat system: panels are defined by hairlines, not shadows.
        panel: '0 0 0 0.5px rgb(255 255 255 / 0.02)',
        cardHover: '0 12px 32px rgb(0 0 0 / 0.4)',
      },
      keyframes: {
        'pulse-dot': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.45' },
        },
        'slide-in': {
          from: { opacity: '0', transform: 'translateY(-6px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'pulse-dot': 'pulse-dot 2.4s ease-in-out infinite',
        'slide-in': 'slide-in 180ms ease-out',
      },
    },
  },
  plugins: [],
};
