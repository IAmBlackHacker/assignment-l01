import * as React from "react";
import { cn } from "./cn";
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "flex h-9 w-full rounded-md border border-border bg-transparent px-3 py-1 text-sm outline-none focus-visible:ring-2 ring-accent",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
