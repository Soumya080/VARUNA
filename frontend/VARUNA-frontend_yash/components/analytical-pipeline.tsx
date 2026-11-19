'use client'

import { useOperatorCaseData } from '@/lib/operator-case-context'
import { PIPELINE, type PipelineStage } from '@/lib/mock-data'
import { cn } from '@/lib/utils'
import {
  Check,
  ChevronRight,
  CircleDot,
  Crosshair,
  GitCompareArrows,
  Radar,
  ShieldCheck,
  Waypoints,
} from 'lucide-react'
import { useState } from 'react'
import type { OperatorCase, ProducerStatus } from '@/lib/operator-case-types'
import { SectionLabel, StatusBadge } from './primitives'

const STAGE_ICONS = [Radar, GitCompareArrows, Waypoints, Crosshair, ShieldCheck, CircleDot]

/** Maps real OperatorCase sections onto the SAME PipelineStage shape the
 * existing component already renders — no visual change, real data. Each
 * row's `.status`/`.detail` come directly from the backend's
 * SectionEnvelope, never invented. */
function useRealPipelineStages(): PipelineStage[] | null {
  const oc = useOperatorCaseData()
  if (!oc) return null

  const sectionToStatus = (status: ProducerStatus): PipelineStage['status'] =>
    status === 'produced' ? 'Completed' : status === 'blocked' ? 'Pending Approval' : 'Pending Approval'

  const stageRow = (
    id: string,
    title: string,
    index: string,
    section: OperatorCase[keyof OperatorCase] & { status: ProducerStatus; reason: string | null; evidence_mode: string | null },
    outputs: Array<{ label: string; value: string }>,
  ): PipelineStage => ({
    id,
    index,
    title,
    status: sectionToStatus(section.status),
    detail:
      section.status === 'produced'
        ? `Produced. Evidence mode: ${section.evidence_mode ?? 'n/a'}.`
        : (section.reason ?? 'Not yet produced.'),
    outputs,
  })

  return [
    stageRow('detection', 'NETRA Detection', '01', oc.detection, [
      { label: 'Status', value: oc.detection.status },
      { label: 'Evidence Mode', value: oc.detection.evidence_mode ?? '—' },
    ]),
    stageRow('origin', 'PRATIVARTAN Reconstruction', '02', oc.origin, [
      { label: 'Status', value: oc.origin.status },
      { label: 'Evidence Mode', value: oc.origin.evidence_mode ?? '—' },
    ]),
    stageRow('attribution', 'NYAYA Attribution', '03', oc.attribution, [
      { label: 'Status', value: oc.attribution.status },
      {
        label: 'Top Posterior',
        value: oc.attribution.value ? oc.attribution.value.top_posterior.toFixed(2) : '—',
      },
    ]),
    stageRow('validity', 'Validity Gate', '04', oc.validity, [
      { label: 'Status', value: oc.validity.status },
      { label: 'State', value: oc.validity.value?.state ?? '—' },
    ]),
    stageRow('forecast', 'PRAVAAH Forecast', '05', oc.forecast, [
      { label: 'Status', value: oc.forecast.status },
      { label: 'Evidence Mode', value: oc.forecast.evidence_mode ?? '—' },
    ]),
    stageRow('mission', 'Mission / Alerts', '06', oc.mission, [
      { label: 'Status', value: oc.mission.status },
      { label: 'Recommendation', value: oc.recommendation },
    ]),
  ]
}

function statusTone(s: PipelineStage['status']): 'ok' | 'warn' {
  return s === 'Pending Approval' ? 'warn' : 'ok'
}

export function AnalyticalPipeline() {
  const [openId, setOpenId] = useState<string | null>(null)
  const realStages = useRealPipelineStages()
  const stages = realStages ?? PIPELINE
  const open = stages.find((s) => s.id === openId)
  const completedCount = stages.filter((s) => s.status !== 'Pending Approval').length

  return (
    <section className="rounded-sm border border-border bg-card p-3.5">
      <div className="mb-3 flex items-center justify-between">
        <SectionLabel>Analytical Pipeline</SectionLabel>
        <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
          {completedCount} of {stages.length} complete
        </span>
      </div>

      <div className="flex items-stretch gap-1 overflow-x-auto scroll-thin pb-1">
        {stages.map((stage, i) => {
          const Icon = STAGE_ICONS[i] ?? CircleDot
          const done = stage.status !== 'Pending Approval'
          const isOpen = openId === stage.id
          return (
            <div key={stage.id} className="flex min-w-0 flex-1 items-center">
              <button
                type="button"
                onClick={() => setOpenId(isOpen ? null : stage.id)}
                aria-expanded={isOpen}
                className={cn(
                  'group flex min-w-[120px] flex-1 flex-col gap-1.5 rounded-sm border p-2.5 text-left transition-colors',
                  isOpen
                    ? 'border-primary/40 bg-primary/5'
                    : 'border-border bg-background/40 hover:border-muted-foreground/30 hover:bg-muted/40',
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[11px] font-semibold text-muted-foreground">
                    {stage.index}
                  </span>
                  <span
                    className={cn(
                      'grid h-5 w-5 place-items-center rounded-full',
                      done
                        ? 'bg-[color-mix(in_oklch,var(--ok)_18%,transparent)] text-[color-mix(in_oklch,var(--ok)_60%,black)]'
                        : 'bg-[color-mix(in_oklch,var(--warn)_20%,transparent)] text-[color-mix(in_oklch,var(--warn)_55%,black)]',
                    )}
                  >
                    {done ? <Check className="h-3 w-3" /> : <Icon className="h-3 w-3" />}
                  </span>
                </div>
                <span className="text-[13px] font-semibold leading-tight text-foreground">
                  {stage.title}
                </span>
                <StatusBadge tone={statusTone(stage.status)} className="w-fit">
                  {stage.status}
                </StatusBadge>
              </button>

              {i < stages.length - 1 && (
                <ChevronRight className="mx-0.5 h-4 w-4 shrink-0 text-muted-foreground/40" />
              )}
            </div>
          )
        })}
      </div>

      {open && (
        <div className="mt-3 rounded-sm border border-border bg-muted/30 p-3">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[11px] font-semibold text-muted-foreground">
              {open.index}
            </span>
            <span className="text-[14px] font-semibold text-foreground">{open.title}</span>
            <StatusBadge tone={statusTone(open.status)} className="ml-auto">
              {open.status}
            </StatusBadge>
          </div>
          <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">
            {open.detail}
          </p>
          <div className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-3">
            {open.outputs.map((o) => (
              <div key={o.label} className="rounded-sm border border-border bg-card px-2.5 py-1.5">
                <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                  {o.label}
                </div>
                <div className="mt-0.5 font-mono text-[13px] font-medium text-foreground">
                  {o.value}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
