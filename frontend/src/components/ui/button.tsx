import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

const button = cva(
  'inline-flex items-center justify-center gap-2 rounded font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50',
  {
    variants: {
      variant: {
        primary: 'bg-accent text-white hover:bg-accent-hover min-h-11 px-5 text-base',
        secondary: 'border border-hairline bg-card text-ink hover:bg-accent-soft min-h-9 px-3 text-sm',
        ghost: 'text-accent hover:bg-accent-soft min-h-9 px-3 text-sm',
      },
    },
    defaultVariants: { variant: 'secondary' },
  },
)

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof button> {
  asChild?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, asChild, ...p }, ref) => {
  const Comp = asChild ? Slot : 'button'
  return <Comp ref={ref} className={cn(button({ variant }), className)} {...p} />
})
Button.displayName = 'Button'
