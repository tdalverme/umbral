import type { HTMLAttributes, LabelHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

type FieldProps = HTMLAttributes<HTMLDivElement> & {
  "data-disabled"?: boolean;
  "data-invalid"?: boolean;
};

export function Field({ className, ...props }: FieldProps) {
  return <div data-slot="field" className={cn("flex flex-col gap-2", className)} {...props} />;
}

export function FieldLabel({ className, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return <label data-slot="field-label" className={cn("text-sm font-medium text-foreground", className)} {...props} />;
}

export function FieldError({ className, children, ...props }: HTMLAttributes<HTMLParagraphElement> & { children?: ReactNode }) {
  if (!children) return null;

  return (
    <p
      role="alert"
      data-slot="field-error"
      className={cn("text-sm text-destructive", className)}
      {...props}
    >
      {children}
    </p>
  );
}
