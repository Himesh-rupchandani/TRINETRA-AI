/** @type {import('tailwindcss').Config} */
export default {
  // Single always-on dark theme ("Sentinel Ops"). The palette is driven by
  // CSS variables in src/index.css :root; the severity/status ramp below is
  // re-tuned for dark surfaces (WCAG-checked against #0D1524 panels).
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      colors: {
        // Surface scale — control room neutrals (see token table in index.css)
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
          soft: 'rgb(var(--brand-soft) / <alpha-value>)',
        },
        // Near-black ink for text sitting on cyan fills (10.4:1 on #22D3EE)
        'on-brand': 'rgb(var(--on-brand) / <alpha-value>)',
        // Warm secondary — accents only
        accent: '#F5A524',
        // Severity / status semantic tokens — dark-tuned ramp
        critical: '#FF3B5C',
        high: '#FF8A3D',
        medium: '#FFC53D',
        low: '#38BDF8',
        info: '#94A3B8',
        online: '#34D399',
        offline: '#F87171',
        degraded: '#FBBF24',
        processing: '#60A5FA',
      },
      fontSize: {
        // Legibility pass: everything is a step larger than a classic dense
        // console so the screen stays readable at arm's length in a control
        // room, or on a duty officer's laptop / projector at 1440x900.
        '2xs': ['0.8125rem', { lineHeight: '1.2rem', letterSpacing: '0.01em' }],
        xs: ['0.875rem', { lineHeight: '1.25rem' }],
        sm: ['0.9375rem', { lineHeight: '1.4rem' }],
        base: ['1rem', { lineHeight: '1.55rem' }],
        lg: ['1.125rem', { lineHeight: '1.7rem' }],
        xl: ['1.3125rem', { lineHeight: '1.85rem' }],
      },
      boxShadow: {
        // Dark UIs read with hairlines, not shadows — keep these whisper-soft.
        panel: '0 1px 2px rgb(0 0 0 / 0.35), 0 8px 28px -18px rgb(0 0 0 / 0.55)',
        cardHover: '0 2px 4px rgb(0 0 0 / 0.4), 0 14px 36px -20px rgb(0 0 0 / 0.7)',
      },
      keyframes: {
        'pulse-ring': {
          '0%': { boxShadow: '0 0 0 0 rgb(255 59 92 / 0.5)' },
          '70%': { boxShadow: '0 0 0 8px rgb(255 59 92 / 0)' },
          '100%': { boxShadow: '0 0 0 0 rgb(255 59 92 / 0)' },
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
