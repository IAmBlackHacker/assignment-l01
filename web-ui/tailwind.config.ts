import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg:       "rgb(var(--bg)/<alpha-value>)",
        fg:       "rgb(var(--fg)/<alpha-value>)",
        muted:    "rgb(var(--muted)/<alpha-value>)",
        accent:   "rgb(var(--accent)/<alpha-value>)",
        border:   "rgb(var(--border)/<alpha-value>)",
      },
    },
  },
} satisfies Config;
