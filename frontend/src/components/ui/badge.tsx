import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-[#1A1A1A] text-white",
        severe: "border-transparent bg-severity-severe text-white",
        emergent: "border-transparent bg-severity-emergent text-white",
        "semi-urgent": "border-transparent bg-severity-semi-urgent text-white",
        "non-urgent": "border-transparent bg-severity-non-urgent text-white",
        outline: "border-[#E5E2DC] text-[#1A1A1A]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
