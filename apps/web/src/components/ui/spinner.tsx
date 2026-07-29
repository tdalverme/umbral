import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Spinner({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      role="status"
      data-slot="spinner"
      className={cn("inline-block size-4 animate-spin rounded-full border-2 border-current border-r-transparent", className)}
      {...props}
    />
  );
}
