import React from "react";
import { cn } from "@/lib/utils";

// Sovereign Kodewaves brand lockup and mark. Fully vector-based (SVG).
// Renders crisply across all themes and viewports without external image dependencies.
export function BrandLogo({
  className,
  inverse = false,
  mark = false,
}: {
  className?: string;
  inverse?: boolean;
  mark?: boolean;
}) {
  const icon = (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("h-full w-auto aspect-square flex-shrink-0", className)}
    >
      <defs>
        <linearGradient id="kodewaves-brand-gradient" x1="2" y1="2" x2="30" y2="30" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#0ea5e9" />
          <stop offset="50%" stopColor="#6366f1" />
          <stop offset="100%" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#kodewaves-brand-gradient)" />
      {/* Symmetrical audio waveform signal */}
      <rect x="6.5" y="12" width="2.5" height="8" rx="1.25" fill="#ffffff" />
      <rect x="11" y="8" width="2.5" height="16" rx="1.25" fill="#ffffff" />
      <rect x="15.5" y="5" width="2.5" height="22" rx="1.25" fill="#ffffff" />
      <rect x="20" y="8.5" width="2.5" height="15" rx="1.25" fill="#ffffff" />
      <rect x="24.5" y="12" width="2.5" height="8" rx="1.25" fill="#ffffff" />
    </svg>
  );

  if (mark) {
    return icon;
  }

  return (
    <div className={cn("inline-flex items-center gap-2.5 select-none", className)}>
      <div className="h-full aspect-square flex items-center justify-center">
        {icon}
      </div>
      <span
        className={cn(
          "font-bold tracking-tight text-lg font-sans leading-none",
          inverse ? "text-white" : "text-foreground"
        )}
      >
        Kodewaves
      </span>
    </div>
  );
}
