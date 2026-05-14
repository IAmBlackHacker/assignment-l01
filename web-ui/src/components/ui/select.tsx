import * as React from "react";
import { cn } from "./cn";
type Props = React.SelectHTMLAttributes<HTMLSelectElement>;
export const Select = React.forwardRef<HTMLSelectElement, Props>(({ className, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      "h-9 rounded-md border border-border bg-bg px-2 text-sm outline-none focus-visible:ring-2 ring-accent",
      className,
    )}
    {...props}
  />
));
Select.displayName = "Select";
