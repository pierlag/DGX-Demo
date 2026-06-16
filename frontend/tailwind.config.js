/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#76b900", // NVIDIA green
          dark: "#5a8c00",
        },
        ink: {
          900: "#0a0e14",
          800: "#0f1623",
          700: "#152032",
          card: "#111a2b",
          border: "#1e2d45",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
