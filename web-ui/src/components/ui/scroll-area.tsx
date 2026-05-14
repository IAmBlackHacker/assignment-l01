import * as React from "react";
import { cn } from "./cn";
export const ScrollArea = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("overflow-y-auto", className)} {...props} />
  ),
);
ScrollArea.displayName = "ScrollArea";
