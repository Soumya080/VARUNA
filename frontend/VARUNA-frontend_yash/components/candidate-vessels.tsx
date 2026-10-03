'use client'

import { VESSELS } from '@/lib/mock-data'
import { cn } from '@/lib/utils'
import { ChevronRight } from 'lucide-react'
import { Meter, StatusBadge } from './primitives'

export function CandidateVessels({
  onSelect,
  selectedId,
}: {
  onSelect: (id: string) => void
  selectedId?: string
}) {
  return (
    <div className="space-y-1.5">
      {VESSELS.map((v) => {
        const lead = v.rank === 1
        const selected = selectedId === v.id
        return (
          <button
            key={v.id}
            type="button"
            onClick={() => onSelect(v.id)}
            className={cn(
              'group block w-full rounded-sm border p-2.5 text-left transition-colors',
              selected
                ? 'border-saffron/50 bg-saffron/5'
                : 'border-border bg-background/40 hover:border-muted-foreground/30 hover:bg-muted/40',
            )}
          >
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  'grid h-5 w-5 shrink-0 place-items-center rounded-sm font-mono text-[11px] font-bold',
                  lead
                    ? 'bg-saffron text-saffron-foreground'
                    : 'bg-muted text-muted-foreground',
                )}
              >
                {v.rank}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[14px] font-semibold leading-tight text-foreground">
                  {v.name}
                </div>
                <div className="truncate text-[12px] text-muted-foreground">{v.type}</div>
              </div>
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5" />
            </div>

            <div className="mt-2 flex items-center justify-between">
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                Attribution Score
              </span>
              <span
                className={cn(
                  'font-mono text-[13px] font-semibold tabular-nums',
                  lead ? 'text-[color-mix(in_oklch,var(--saffron)_50%,black)]' : 'text-foreground',
                )}
              >
                {v.attributionScore}%
              </span>
            </div>
            <Meter
              value={v.attributionScore}
              tone={lead ? 'saffron' : 'muted'}
              className="mt-1"
            />
            {lead && (
              <div className="mt-2">
                <StatusBadge tone="saffron" dot>
                  Primary Lead
                </StatusBadge>
              </div>
            )}
          </button>
        )
      })}
    </div>
  )
}
