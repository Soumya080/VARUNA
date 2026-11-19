'use client'

/**
 * Loading / error boundary for the OperatorCase fetch. Uses the EXISTING
 * design language (border-border/bg-card panels, font-mono uppercase
 * labels) rather than introducing a new visual style for these states.
 */
import { AlertTriangle, Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { useOperatorCase } from '@/lib/operator-case-context'

export function OperatorCaseBoundary({ children }: { children: ReactNode }) {
  const state = useOperatorCase()

  if (state.status === 'loading') {
    return (
      <div className="flex min-h-[240px] flex-col items-center justify-center gap-2 rounded-sm border border-border bg-card p-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
        <p className="font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
          Loading case from VARUNA backend…
        </p>
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div
        role="alert"
        className="flex min-h-[240px] flex-col items-center justify-center gap-2 rounded-sm border border-[color-mix(in_oklch,var(--destructive)_40%,transparent)] bg-[color-mix(in_oklch,var(--destructive)_6%,transparent)] p-8 text-center"
      >
        <AlertTriangle className="h-5 w-5 text-destructive" aria-hidden="true" />
        <p className="font-mono text-[12px] uppercase tracking-[0.1em] text-destructive">
          Could not load case
        </p>
        <p className="max-w-md text-[13px] leading-relaxed text-muted-foreground">
          {state.error}
        </p>
      </div>
    )
  }

  return <>{children}</>
}
