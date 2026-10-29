import Image from "next/image";
import React from "react";

import { cn } from "@/lib/utils";

// Shared Kodewaves brand lockup. The mark is also the App Router icon at
// src/app/icon.svg, so the in-app and browser-tab marks stay identical.
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
    <Image
      src="/icon.svg"
      alt=""
      width={32}
      height={32}
      aria-hidden="true"
      draggable={false}
      unoptimized
      className={cn("h-full w-auto aspect-square flex-shrink-0", className)}
    />
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
