/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    '../templates/**/*.html',
    '../core/templates/**/*.html',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#1E40AF',
          light: '#1E40AF',
          dark: '#1E40AF',
        },
        secondary: {
          DEFAULT: '#6B7280',
          light: '#6B7280',
          dark: '#6B7280',
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
}
