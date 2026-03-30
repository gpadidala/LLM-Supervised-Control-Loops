/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        regime: {
          normal: '#22c55e',
          degraded: '#eab308',
          critical: '#ef4444',
          recovery: '#3b82f6',
          maintenance: '#a855f7',
        },
      },
      animation: {
        'pulse-critical': 'pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}
