import * as React from "react";
import { cn } from "./cn";

type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "ghost" | "danger";
  size?: "sm" | "md" | "icon";
};

export const Button = React.forwardRef<HTMLButtonElement, Props>(
  ({ className, variant = "default", size = "md", ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center rounded-md font-medium transition outline-none focus-visible:ring-2 ring-accent disabled:opacity-50 disabled:cursor-not-allowed",
        variant === "default" && "bg-accent text-bg hover:opacity-90",
        variant === "ghost" && "bg-transparent hover:bg-border text-fg",
        variant === "danger" && "bg-red-500 text-white hover:opacity-90",
        size === "sm" && "px-2 py-1 text-sm h-8",
        size === "md" && "px-3 py-2 text-sm h-9",
        size === "icon" && "h-9 w-9 p-0",
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = "Button";
