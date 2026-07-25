/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#FAF8F5",
        card: "#FFFFFF",
        border: "#E5E2DC",
        "text-primary": "#1A1A1A",
        "text-secondary": "#6B6B6B",
        severity: {
          critical: "#C73E3A",
          urgent: "#E07A1F",
          routine: "#3A5FC7",
          fyi: "#6B6B6B",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        serif: ["Source Serif 4", "Georgia", "serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        card: "12px",
      },
      keyframes: {
        "slide-in": {
          "0%": { opacity: "0", transform: "translateY(-12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "highlight-fade": {
          "0%": { backgroundColor: "rgba(58, 95, 199, 0.12)" },
          "100%": { backgroundColor: "transparent" },
        },
      },
      animation: {
        "slide-in": "slide-in 0.35s ease-out",
        "highlight-fade": "highlight-fade 1.5s ease-out",
      },
    },
  },
  plugins: [],
}
