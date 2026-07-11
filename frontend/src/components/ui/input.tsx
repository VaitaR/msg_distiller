import type { InputHTMLAttributes } from 'react'

import { cn } from '../../lib/utils'

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        'flex h-10 w-full rounded-2xl border border-input bg-white/80 px-4 py-2 text-sm shadow-sm placeholder:text-muted-foreground',
        className,
      )}
      {...props}
    />
  )
}