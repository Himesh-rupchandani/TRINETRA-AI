/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      spacing: {
        '7.5': '1.875rem',
        '8.5': '2.125rem',
        '4.5': '1.125rem',
      },
      fontFamily: {
        sans: ['"Public Sans"', 'Inter', 'Segoe UI', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      colors: {
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
        accent: {
          DEFAULT: 'rgb(var(--accent) / <alpha-value>)',
          strong: 'rgb(var(--accent-strong) / <alpha-value>)',
          weak: 'rgb(var(--accent-weak) / <alpha-value>)',
        },
        // Status — text-grade on white
        online: 'rgb(var(--status-online) / <alpha-value>)',
        offline: 'rgb(var(--status-offline) / <alpha-value>)',
        warn: 'rgb(var(--status-warn) / <alpha-value>)',
        'info': 'rgb(var(--status-info) / <alpha-value>)',
        // Severity ramp (chips/text on tints)
        critical: '#be123c',
        high: '#c2410c',
        medium: '#a16207',
        low: '#0369a1',
      },
      fontSize: {
        '2xs': ['0.8125rem', { lineHeight: '1.15rem' }],
        xs: ['0.8125rem', { lineHeight: '1.25rem' }],
        sm: ['0.875rem', { lineHeight: '1.35rem' }],
        base: ['0.9375rem', { lineHeight: '1.5rem' }],
      },
      boxShadow: {
        xs: '0 1px 2px 0 rgb(16 24 40 / 0.05)',
        sm: '0 1px 3px rgb(16 24 40 / 0.08), 0 1px 2px rgb(16 24 40 / 0.04)',
        md: '0 6px 16px -4px rgb(16 24 40 / 0.10), 0 2px 6px -2px rgb(16 24 40 / 0.05)',
        lg: '0 16px 40px -12px rgb(16 24 40 / 0.18)',
      },
      keyframes: {
        'pulse-dot': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.35' },
        },
      },
      animation: {
        'pulse-dot': 'pulse-dot 2.2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
