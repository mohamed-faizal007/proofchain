import type { Config } from "tailwindcss";

// Design tokens. `gray` is a cool, violet-tinted ink scale (950 page → 900 surface → 800 raised →
// 700 borders); `blue` is remapped to the single brand accent so every existing blue-* utility
// (primary buttons, links, focus rings) follows it. Verdict colours (green/amber/red) are untouched.
const ink = {
  50: "#f7f7fb",
  100: "#eeeef6",
  200: "#dcdcea",
  300: "#bdbdd1",
  400: "#9696b0",
  500: "#71718c",
  600: "#50506b",
  700: "#34344d",
  800: "#1f1f31",
  900: "#141420",
  950: "#0b0b13",
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
        glow: "0 0 0 1px rgb(125 104 251 / 0.35), 0 8px 24px -8px rgb(106 80 242 / 0.55)",
      },
    },
  },
  plugins: [],
} satisfies Config;
