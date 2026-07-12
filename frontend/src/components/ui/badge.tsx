import { cva, type VariantProps } from 'class-variance-authority'
import type { HTMLAttributes } from 'react'

import { cn } from '../../lib/utils'

const badgeVariants = cva('inline-flex items-center rounded-full px-3 py-1 text-xs font-medium', {
  variants: {
    variant: {
      default: 'bg-secondary text-secondary-foreground',
      warning: 'bg-amber-100 text-amber-900',
      success: 'bg-emerald-100 text-emerald-900',
      danger: 'bg-rose-100 text-rose-900',
      info: 'bg-sky-100 text-sky-900',
    },
  },
  defaultVariants: {
    variant: 'default',
  },
})

type BadgeProps = HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant, className }))} {...props} />
}
