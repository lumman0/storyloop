import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const buttonVariants = cva("ui-button", {
  variants: {
    variant: {
      primary: "ui-button-primary",
      secondary: "ui-button-secondary",
      ghost: "ui-button-ghost",
    },
    size: {
      default: "ui-button-default",
      small: "ui-button-small",
      icon: "ui-button-icon",
    },
  },
  defaultVariants: { variant: "primary", size: "default" },
});

export function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Component = asChild ? Slot : "button";
  return (
    <Component
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}
