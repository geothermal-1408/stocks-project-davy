/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: '#080b0f',
          card: '#0d1117',
          panel: '#161b22',
          hover: '#1c2128',
        },
        accent: {
          mint: '#00e5a0',
          danger: '#ff3b30',
          warning: '#f5a623',
          purple: '#a855f7',
          cyan: '#06b6d4',
        },
        text: {
          primary: '#e6edf3',
          muted: '#8b949e',
        },
        border: {
          DEFAULT: '#1c2128',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'monospace'],
        display: ['"Barlow Condensed"', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
