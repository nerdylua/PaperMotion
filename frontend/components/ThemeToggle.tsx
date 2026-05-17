"use client";

import { useTheme } from "next-themes";
import { Moon, Sun } from "lucide-react";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme !== "light";

  return (
    <button
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="fixed top-6 right-6 z-50 flex h-10 w-10 items-center justify-center rounded-full bg-white/[0.05] border border-white/[0.15] text-white/80 hover:bg-white/[0.1] hover:text-white transition-all shadow-[0_0_20px_rgba(var(--shard-rgb),0.05)] hover:shadow-[0_0_30px_rgba(var(--shard-rgb),0.1)]"
      aria-label="Toggle theme"
    >
      {isDark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
    </button>
  );
}
