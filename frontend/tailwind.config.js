/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'black-base': "var(--color-black-base)",
        'black-base-80': "var(--color-black-base-80)",
        'white-base': "var(--color-white-base)",
        
        'background': "var(--color-background)",
        'background-20': "var(--color-background-20)",
        'surface': "var(--color-surface)",
        'surface-50': "var(--color-surface-50)",
        'surface-80': "var(--color-surface-80)",
        'surface-elevated': "var(--color-surface-elevated)",

        'text-primary': "var(--color-text-primary)",
        'text-secondary': "var(--color-text-secondary)",
        'text-muted': "var(--color-text-muted)",
        'text-disabled': "var(--color-text-disabled)",
        'text-inverse': "var(--color-text-inverse)",

        'border-dark': "var(--color-border-dark)",
        'border-subtle': "var(--color-border-subtle)",
        'border-subtle-50': "var(--color-border-subtle-50)",
        'border-strong': "var(--color-border-strong)",
        'border-highlight': "var(--color-border-highlight)",

        'status': "var(--color-status)",
        'status-75': "var(--color-status-75)",

        'success': "var(--color-success)",
        'success-75': "var(--color-success-75)",

        'accent-light': "var(--color-accent-light)",
        'accent': "var(--color-accent)",
        'accent-dark': "var(--color-accent-dark)",
        'accent-dark-20': "var(--color-accent-dark-20)",
        'accent-dark-40': "var(--color-accent-dark-40)",
        'accent-dark-50': "var(--color-accent-dark-50)",

        'danger-light': "var(--color-danger-light)",
        'danger': "var(--color-danger)",
        'danger-30': "var(--color-danger-30)",
        'danger-dark': "var(--color-danger-dark)",
        'danger-darkest-20': "var(--color-danger-darkest-20)",

        'info-light': "var(--color-info-light)",
        'info-20': "var(--color-info-20)",
        'info-30': "var(--color-info-30)",
        'info': "var(--color-info)",
        'info-dark-20': "var(--color-info-dark-20)",
        'info-dark-40': "var(--color-info-dark-40)",
        'info-dark-50': "var(--color-info-dark-50)",
        'info-dark': "var(--color-info-dark)",

        'warning-20': "var(--color-warning-20)",
        'warning-30': "var(--color-warning-30)",
        'warning': "var(--color-warning)",
        'warning-dark-20': "var(--color-warning-dark-20)",
        'warning-dark-40': "var(--color-warning-dark-40)",
        'warning-dark-50': "var(--color-warning-dark-50)",
        'warning-dark': "var(--color-warning-dark)"
      }
    }
  },
  plugins: [],
}
