import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        ev: {
          bg:    '#0a0d0f',
          green: '#00dc6e',
          red:   '#ff4d4d',
          gold:  '#ffc800',
          blue:  '#80a8ff',
        },
      },
      fontFamily: {
        mono: ['var(--font-mono)', 'monospace'],
        syne: ['var(--font-syne)', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
export default config;
