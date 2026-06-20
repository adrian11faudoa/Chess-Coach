/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        board: {
          light: '#F0D9B5',
          dark:  '#B58863',
          'light-highlight': '#CDD26A',
          'dark-highlight':  '#AABA44',
          'selected': 'rgba(20,85,30,0.5)',
        },
        surface: {
          DEFAULT: '#1e1e1e',
          2: '#252525',
          3: '#2a2a2a',
          4: '#333333',
        },
        accent: '#2979FF',
        'accent-hover': '#1565C0',
      },
      fontFamily: {
        mono: ['"Courier New"', 'monospace'],
      }
    }
  },
  plugins: []
}
