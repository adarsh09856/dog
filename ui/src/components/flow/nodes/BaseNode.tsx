import { forwardRef, HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export const BaseNode = forwardRef<
    HTMLDivElement,
    HTMLAttributes<HTMLDivElement> & {
        selected?: boolean;
        invalid?: boolean;
        selected_through_edge?: boolean;
        hovered_through_edge?: boolean;
        runtimeActive?: boolean;
    }
>(({ children, className, selected, invalid, selected_through_edge, hovered_through_edge, runtimeActive, ...props }, ref) => (
    <div
        ref={ref}
        className={cn(
            // Base styling - larger with max width, uses semantic colors
            "relative rounded-lg border bg-card text-card-foreground min-w-[320px] max-w-[400px] min-h-[120px]",
            // Border styling
            "border-border",
            className,
            // Selected state - prominent halo effect
            selected ? "border-primary ring-2 ring-primary/40 shadow-md" : "",
            // Invalid state
            invalid ? "border-destructive shadow-[0_0_10px_rgba(239,68,68,0.3)]" : "",
            // Hovered through edge takes precedence over selected through edge
            hovered_through_edge ? "ring-2 ring-primary/60 shadow-md" : "",
            !hovered_through_edge && selected_through_edge ? "ring-1 ring-primary/50 shadow-sm" : "",
            runtimeActive ? "ring-2 ring-primary/60 shadow-md" : "",
            !selected_through_edge && !hovered_through_edge && "hover:border-muted-foreground/50",
        )}
        tabIndex={0}
        {...props}
    >
        {children}
    </div>
));

BaseNode.displayName = "BaseNode";
