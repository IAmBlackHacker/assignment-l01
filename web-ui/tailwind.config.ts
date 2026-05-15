import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg:       "rgb(var(--bg)/<alpha-value>)",
        surface:  "rgb(var(--surface)/<alpha-value>)",
        fg:       "rgb(var(--fg)/<alpha-value>)",
        muted:    "rgb(var(--muted)/<alpha-value>)",
        accent:   "rgb(var(--accent)/<alpha-value>)",
        "accent-2": "rgb(var(--accent-2)/<alpha-value>)",
        border:   "rgb(var(--border)/<alpha-value>)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        display: ['"Inter Tight"', "Inter", "sans-serif"],
        mono: ["Inconsolata", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [typography],
} satisfies Config;
