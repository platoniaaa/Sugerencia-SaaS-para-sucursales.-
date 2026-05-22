import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Azul corporativo (acento principal).
        brand: {
          DEFAULT: "#1e40af",
          50: "#eff4ff",
          100: "#dbe6fe",
          600: "#1e40af",
          700: "#1b3a9c",
          800: "#1a3486",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
