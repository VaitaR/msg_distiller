import type { TextareaHTMLAttributes } from 'react'

import { cn } from '../../lib/utils'

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        'flex min-h-24 w-full rounded-3xl border border-input bg-white/80 px-4 py-3 text-sm shadow-sm placeholder:text-muted-foreground',
        className,
      )}
      {...props}
    />
  )
}