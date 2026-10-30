"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ThemeToggleProps {
  className?: string;
  showLabel?: boolean;
  variant?: "ghost" | "outline" | "default";
  size?: "default" | "sm" | "lg" | "icon";
}

export default function ThemeToggle({
  className,
  showLabel = false,
  variant = "ghost",
  size = "icon"
}: ThemeToggleProps) {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const toggleTheme = () => {
    setTheme(resolvedTheme === "light" ? "dark" : "light");
  };
  const theme = mounted ? (resolvedTheme === "light" ? "light" : "dark") : null;

  return (
    <Button
      variant={variant}
      size={size}
      disabled={!mounted}
      className={cn(
        showLabel && "w-full justify-start",
        className
      )}
      onClick={toggleTheme}
    >
      <Sun className={cn(
        "h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0",
        showLabel && "absolute"
      )} />
      <Moon className={cn(
        "h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100",
        !showLabel && "absolute"
      )} />
      {showLabel && theme && (
        <span className="ml-2">{theme === "light" ? "Light" : "Dark"} Mode</span>
      )}
      <span className="sr-only">Toggle theme</span>
    </Button>
  );
}
