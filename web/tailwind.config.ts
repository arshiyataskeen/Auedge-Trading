import type { Config } from 'tailwindcss'

const v = (name: string) => `var(--${name})`

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        app: v('app'), bg: v('bg'), panel2: v('panel2'), hover: v('hover'),
        line: v('line'), line2: v('line2'), text: v('text'), strong: v('strong'), muted: v('muted'), faint: v('faint'),
        up: v('up'), down: v('down'), accent: v('accent'), accent2: v('accent2'), warn: v('warn'),
        'up-bg': v('up-bg'), 'down-bg': v('down-bg'), 'warn-bg': v('warn-bg'), 'acc-bg': v('acc-bg'),
        rowhover: v('rowhover'), rowhover2: v('rowhover2'),
      },
    },
  },
  plugins: [],
} satisfies Config
