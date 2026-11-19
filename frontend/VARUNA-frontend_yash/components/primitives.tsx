'use client'

import { cn } from '@/lib/utils'
import { Info } from 'lucide-react'
import type { ReactNode } from 'react'

/* ------------------------------------------------------------------ */
/* Section label — small uppercase government-style caption            */
/* ------------------------------------------------------------------ */

export function SectionLabel({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <h3
      className={cn(
        'font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground',
        className,
      )}
    >
      {children}
    </h3>
  )
}

/* ------------------------------------------------------------------ */
/* Status badge                                                        */
/* ------------------------------------------------------------------ */

type Tone = 'ok' | 'warn' | 'destructive' | 'navy' | 'saffron' | 'muted'

const toneClasses: Record<Tone, string> = {
  ok: 'border-[color-mix(in_oklch,var(--ok)_40%,transparent)] bg-[color-mix(in_oklch,var(--ok)_14%,transparent)] text-[color-mix(in_oklch,var(--ok)_65%,black)]',
  warn: 'border-[color-mix(in_oklch,var(--warn)_45%,transparent)] bg-[color-mix(in_oklch,var(--warn)_16%,transparent)] text-[color-mix(in_oklch,var(--warn)_60%,black)]',
  destructive:
    'border-[color-mix(in_oklch,var(--destructive)_40%,transparent)] bg-[color-mix(in_oklch,var(--destructive)_12%,transparent)] text-destructive',
  navy: 'border-[color-mix(in_oklch,var(--navy)_25%,transparent)] bg-[color-mix(in_oklch,var(--navy)_10%,transparent)] text-primary',
  saffron:
    'border-[color-mix(in_oklch,var(--saffron)_50%,transparent)] bg-[color-mix(in_oklch,var(--saffron)_18%,transparent)] text-[color-mix(in_oklch,var(--saffron)_55%,black)]',
  muted: 'border-border bg-muted text-muted-foreground',
}

export function StatusBadge({
  children,
  tone = 'muted',
  dot = false,
  className,
}: {
  children: ReactNode
  tone?: Tone
  dot?: boolean
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-sm border px-1.5 py-0.5 font-mono text-[11px] font-medium uppercase tracking-[0.08em]',
        toneClasses[tone],
        className,
      )}
    >
      {dot && (
        <span
          className="h-1.5 w-1.5 rounded-full bg-current"
          aria-hidden="true"
        />
      )}
      {children}
    </span>
  )
}

/* ------------------------------------------------------------------ */
/* Meter — horizontal progress bar                                     */
/* ------------------------------------------------------------------ */

export function Meter({
  value,
  tone = 'navy',
  className,
  trackClassName,
}: {
  value: number
  tone?: 'navy' | 'saffron' | 'teal' | 'muted'
  className?: string
  trackClassName?: string
}) {
  const color =
    tone === 'saffron'
      ? 'var(--saffron)'
      : tone === 'teal'
        ? 'var(--teal)'
        : tone === 'muted'
          ? 'var(--muted-foreground)'
          : 'var(--navy)'
  return (
    <div
      className={cn('h-1.5 w-full overflow-hidden rounded-full bg-muted', trackClassName)}
      role="progressbar"
      aria-valuenow={Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={cn('h-full rounded-full transition-[width] duration-500', className)}
        style={{ width: `${Math.max(0, Math.min(100, value))}%`, backgroundColor: color }}
      />
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* InfoTip — hover tooltip for technical terms                         */
/* ------------------------------------------------------------------ */

export function InfoTip({ label }: { label: string }) {
  return (
    <span className="group/tip relative inline-flex align-middle">
      <button
        type="button"
        className="inline-flex text-muted-foreground/70 transition-colors hover:text-foreground focus:outline-none focus-visible:text-foreground"
        aria-label={label}
      >
        <Info className="h-3 w-3" aria-hidden="true" />
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-1.5 w-52 -translate-x-1/2 rounded-sm border border-border bg-popover px-2.5 py-1.5 text-left text-[12px] leading-snug text-popover-foreground opacity-0 shadow-md transition-opacity duration-150 group-hover/tip:opacity-100"
      >
        {label}
      </span>
    </span>
  )
}
