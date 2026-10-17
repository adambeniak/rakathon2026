import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

// Targets are 48px tall; `size="sm"` (40px) only inside dense rows. Disabled is 45% opacity.
const button = cva(
  'inline-flex items-center justify-center gap-2 rounded-md border-[1.5px] font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-[.45]',
  {
    variants: {
      variant: {
        primary:
          'border-accent bg-accent text-accent-on hover:border-accent-hover hover:bg-accent-hover',
        secondary: 'border-line-strong bg-card text-ink hover:bg-sunken',
        ghost: 'border-transparent text-accent hover:bg-accent-soft',
      },
      size: {
        md: 'min-h-12 px-6 text-base',
        sm: 'min-h-10 px-4 text-sm',
      },
    },
    compoundVariants: [
      // Secondary and ghost buttons sit in rows beside content: a step quieter than the one primary action.
      { variant: 'secondary', size: 'md', className: 'px-5 text-sm' },
      { variant: 'ghost', size: 'md', className: 'px-3 text-sm' },
    ],
    defaultVariants: { variant: 'secondary', size: 'md' },
  },
)

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof button> {
  asChild?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, ...p }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return <Comp ref={ref} className={cn(button({ variant, size }), className)} {...p} />
  },
)
Button.displayName = 'Button'
