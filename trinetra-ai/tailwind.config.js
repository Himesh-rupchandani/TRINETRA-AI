/** @type {import('tailwindcss').Config} */
export default {
  // Light Mode only: Night/Dark Mode was removed, so there is no darkMode
  // variant ('class'/'media') registered here anymore.
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      colors: {
        // Surface scale — control room neutrals
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
          // Filled-control variant — dark-enough azure that white labels pass AA.
          strong: 'rgb(var(--brand-strong) / <alpha-value>)',
          soft: 'rgb(var(--brand-soft) / <alpha-value>)',
        },
        // Severity / status semantic tokens — tuned for dark surfaces
        critical: '#f43f5e',
        high: '#fb923c',
        medium: '#eab308',
        low: '#38bdf8',
        info: '#94a3b8',
        online: '#22c55e',
        offline: '#ef4444',
        degraded: '#f59e0b',
        processing: '#3b82f6',
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
        panel: '0 1px 2px rgb(0 0 0 / 0.45), 0 1px 8px rgb(0 0 0 / 0.35)',
        cardHover: '0 6px 20px rgb(0 0 0 / 0.5), 0 0 0 1px rgb(var(--line) / 0.9)',
      },
      keyframes: {
        'pulse-ring': {
          '0%': { boxShadow: '0 0 0 0 rgb(244 63 94 / 0.45)' },
          '70%': { boxShadow: '0 0 0 8px rgb(244 63 94 / 0)' },
          '100%': { boxShadow: '0 0 0 0 rgb(244 63 94 / 0)' },
        },
        'slide-in': {
          from: { opacity: '0', transform: 'translateY(-6px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'pulse-ring': 'pulse-ring 2s infinite',
        'slide-in': 'slide-in 160ms ease-out',
      },
    },
  },
  plugins: [],
};
