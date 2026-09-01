'use client'

import { CURRENT_MISSION_STATE, MISSION_STATES } from '@/lib/mock-data'
import { cn } from '@/lib/utils'
import { Check, FileSearch, ShieldCheck } from 'lucide-react'
import { SectionLabel } from './primitives'

export function MissionStatus() {
  const currentIdx = MISSION_STATES.indexOf(CURRENT_MISSION_STATE)

  return (
    <section className="rounded-sm border border-border bg-card p-3.5">
      <div className="mb-3 flex items-center justify-between">
        <SectionLabel>Mission Status</SectionLabel>
        <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-[color-mix(in_oklch,var(--warn)_55%,black)]">
          Awaiting authorization
        </span>
      </div>

      {/* State track */}
      <ol className="flex items-center gap-1 overflow-x-auto scroll-thin pb-1">
        {MISSION_STATES.map((state, i) => {
          const done = i < currentIdx
          const current = i === currentIdx
          return (
            <li key={state} className="flex flex-1 items-center gap-1">
              <div
                className={cn(
                  'flex min-w-[92px] flex-1 items-center gap-2 rounded-sm border px-2.5 py-2',
                  current
                    ? 'border-[color-mix(in_oklch,var(--warn)_45%,transparent)] bg-[color-mix(in_oklch,var(--warn)_12%,transparent)]'
                    : done
                      ? 'border-[color-mix(in_oklch,var(--ok)_35%,transparent)] bg-[color-mix(in_oklch,var(--ok)_8%,transparent)]'
                      : 'border-border bg-background/40',
                )}
              >
                <span
                  className={cn(
                    'grid h-4 w-4 shrink-0 place-items-center rounded-full font-mono text-[9px] font-bold',
                    current
                      ? 'bg-[var(--warn)] text-[oklch(0.22_0.03_60)]'
                      : done
                        ? 'bg-[var(--ok)] text-primary-foreground'
                        : 'bg-muted text-muted-foreground',
                  )}
                >
                  {done ? <Check className="h-2.5 w-2.5" /> : i + 1}
                </span>
                <span
                  className={cn(
                    'truncate font-mono text-[10px] font-semibold uppercase tracking-[0.06em]',
                    current
                      ? 'text-[color-mix(in_oklch,var(--warn)_55%,black)]'
                      : done
                        ? 'text-[color-mix(in_oklch,var(--ok)_55%,black)]'
                        : 'text-muted-foreground',
                  )}
                >
                  {state}
                </span>
              </div>
              {i < MISSION_STATES.length - 1 && (
                <span
                  className={cn(
                    'h-px w-2 shrink-0',
                    done ? 'bg-[var(--ok)]' : 'bg-border',
                  )}
                  aria-hidden="true"
                />
              )}
            </li>
          )
        })}
      </ol>

      {/* Actions */}
      <div className="mt-3.5 flex flex-col gap-2 sm:flex-row">
        <button
          type="button"
          className="flex flex-1 items-center justify-center gap-1.5 rounded-sm bg-primary px-4 py-2.5 text-[12px] font-semibold uppercase tracking-[0.08em] text-primary-foreground transition-colors hover:bg-[var(--navy-muted)]"
        >
          <ShieldCheck className="h-4 w-4" />
          Request Authorization
        </button>
        <button
          type="button"
          className="flex items-center justify-center gap-1.5 rounded-sm border border-border bg-background px-4 py-2.5 text-[12px] font-semibold uppercase tracking-[0.08em] text-foreground transition-colors hover:bg-muted sm:flex-none"
        >
          <FileSearch className="h-4 w-4" />
          Review Evidence
        </button>
      </div>
    </section>
  )
}
