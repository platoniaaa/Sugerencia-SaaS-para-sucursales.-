import * as React from "react";
import { cn } from "@/lib/utils";

export function Badge({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
        className
      )}
      {...props}
    />
  );
}

/** Devuelve clases de color para una clasificacion ABC. */
export function colorABC(abc: string | null | undefined): string {
  switch ((abc ?? "").toUpperCase()) {
    case "A":
      return "bg-emerald-100 text-emerald-700";
    case "B":
      return "bg-amber-100 text-amber-700";
    case "C":
      return "bg-slate-200 text-slate-600";
    default:
      return "bg-slate-100 text-slate-500";
  }
}
