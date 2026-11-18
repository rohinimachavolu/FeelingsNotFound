/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"] },
      colors: {
        ink: { DEFAULT: "#1f2a37", soft: "#4b5563", faint: "#6b7280" },
        accent: { DEFAULT: "#0f5f6b", soft: "#e6f2f3", strong: "#0b4a53" },
      },
    },
  },
  plugins: [],
};
