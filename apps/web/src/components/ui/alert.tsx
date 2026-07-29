import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Alert({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="alert"
      data-slot="alert"
      className={cn("relative w-full rounded-lg border border-border bg-card p-4 text-card-foreground", className)}
      {...props}
    />
  );
}

export function AlertTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h5 data-slot="alert-title" className={cn("mb-1 font-medium leading-none tracking-tight", className)} {...props} />;
}

export function AlertDescription({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="alert-description" className={cn("text-sm text-muted-foreground", className)} {...props} />;
}
