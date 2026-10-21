import type { Config } from "tailwindcss";

// Design tokens. `gray` is a cool, violet-tinted ink scale (950 page → 900 surface → 800 raised →
// 700 borders); `blue` is remapped to the single brand accent so every existing blue-* utility
// (primary buttons, links, focus rings) follows it. Verdict colours (green/amber/red) are untouched.
const ink = {
  50: "#f6f6fb",
  100: "#ececf5",
  200: "#dadae8",
  300: "#bbbbd0",
  400: "#9494af",
  500: "#6f6f8b",
  600: "#4e4e69",
  700: "#2c2c43",
  800: "#1a1a2b",
  900: "#11111c",
  950: "#08080f",
};

const accent = {
  50: "#f1efff",
  100: "#e5e1ff",
  200: "#cdc6ff",
  300: "#afa4ff",
  400: "#9484ff",
  500: "#7d68fb",
  600: "#6a50f2",
  700: "#5a41d8",
  800: "#4a35ae",
  900: "#3a2d85",
  950: "#221b52",
};

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { gray: ink, blue: accent },
      fontFamily: {
        sans: ['"Inter"', "ui-sans-serif", "system-ui", "sans-serif"],
        display: ['"Space Grotesk"', '"Inter"', "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        soft: "0 1px 2px rgb(20 20 40 / 0.04), 0 8px 24px -12px rgb(20 20 60 / 0.12)",
        lifted: "0 2px 4px rgb(20 20 40 / 0.04), 0 18px 40px -16px rgb(40 30 120 / 0.28)",
        glow: "0 0 0 1px rgb(125 104 251 / 0.35), 0 8px 24px -8px rgb(106 80 242 / 0.55)",
      },
    },
  },
  plugins: [],
} satisfies Config;
