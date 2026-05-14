import * as React from "react";
import { cn } from "./cn";
export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-2 ring-accent resize-none",
        className,
      )}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";
