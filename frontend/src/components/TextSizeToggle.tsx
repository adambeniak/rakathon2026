import { useEffect, useState } from 'react'
import { shell } from '@/i18n/cs/shell'
import { cn } from '@/lib/cn'

/** Root font size when "A+ Větší písmo" is on: every size is in rem, so the whole page scales by 12.5 %. */
const LARGE_TEXT_ROOT_SIZE = '112.5%'
const KEY = 'stafeta.largeText'

function readStored(): boolean {
  try {
    return window.localStorage.getItem(KEY) === '1'
  } catch {
    return false // storage blocked (private mode, sandbox): the switch still works for this page view
  }
}

function store(on: boolean): void {
  try {
    window.localStorage.setItem(KEY, on ? '1' : '0')
  } catch {
    // Not persisted; the current page keeps the chosen size.
  }
}

/** "A+ Větší písmo": a pressed/unpressed button in the app bar. On phones only "A+" shows. */
export function TextSizeToggle({ className }: { className?: string }) {
  const [on, setOn] = useState(readStored)

  useEffect(() => {
    document.documentElement.style.fontSize = on ? LARGE_TEXT_ROOT_SIZE : ''
  }, [on])

  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={() => {
        const next = !on
        store(next)
        setOn(next)
      }}
      className={cn(
        'inline-flex min-h-12 min-w-12 items-center justify-center gap-2 rounded-md border-[1.5px] px-3 text-sm font-semibold transition-colors',
        on
          ? 'border-accent bg-accent-soft text-accent'
          : 'border-line-strong bg-card text-ink hover:bg-sunken',
        className,
      )}
    >
      <span aria-hidden className="text-base font-semibold">
        {shell.textSize.short}
      </span>
      <span className="sr-only sm:not-sr-only">{shell.textSize.label}</span>
    </button>
  )
}
