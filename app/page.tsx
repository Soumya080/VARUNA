'use client'

import { useState } from 'react'
import { AnalyticalPipeline } from '@/components/analytical-pipeline'
import { AssignmentTable } from '@/components/assignment-table'
import { CaseIntelligence } from '@/components/case-intelligence'
import { CaseSummary } from '@/components/case-summary'
import { FeasibilitySummary } from '@/components/feasibility-summary'
import type { MapDetail } from '@/components/map/map-utils'
import { MapView } from '@/components/map/map-view'
import { MissionStatus } from '@/components/mission-status'

export default function Page() {
  const [detail, setDetail] = useState<MapDetail | null>(null)
  const selectedVesselId = detail?.type === 'vessel' ? detail.id : undefined

  return (
    <>
      {/* Page heading */}
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-lg font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Source Reconstruction &amp; Vessel Attribution
          </h1>
          <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
            Case 24-071 · Arabian Sea · Restricted
          </p>
        </div>
        <span className="rounded-sm border border-border bg-card px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
          Last sync · 06:44 UTC
        </span>
      </div>

      <CaseSummary />

      {/* Map + intelligence */}
      <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-[1fr_360px]">
        <MapView onSelectDetail={setDetail} selectedVesselId={selectedVesselId} />
        <div className="min-h-[420px] xl:h-auto">
          <CaseIntelligence
            onSelectVessel={(id) => setDetail({ type: 'vessel', id })}
            selectedVesselId={selectedVesselId}
          />
        </div>
      </div>

      {/* Pipeline */}
      <div className="mt-3">
        <AnalyticalPipeline />
      </div>

      {/* Assignment + feasibility */}
      <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-[1fr_320px]">
        <AssignmentTable />
        <FeasibilitySummary />
      </div>

      {/* Mission */}
      <div className="mt-3">
        <MissionStatus />
      </div>
    </>
  )
}
