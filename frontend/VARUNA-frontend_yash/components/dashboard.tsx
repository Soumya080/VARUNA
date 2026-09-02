'use client'

import { useState } from 'react'
import { AnalyticalPipeline } from './analytical-pipeline'
import { AssignmentTable } from './assignment-table'
import { CaseIntelligence } from './case-intelligence'
import { CaseSummary } from './case-summary'
import { DetailDrawer } from './detail-drawer'
import { FeasibilitySummary } from './feasibility-summary'
import { Header } from './header'
import type { MapDetail } from './map/map-utils'
import { MapView } from './map/map-view'
import { MissionStatus } from './mission-status'
import { Sidebar } from './sidebar'

export function Dashboard() {
  const [navOpen, setNavOpen] = useState(false)
  const [detail, setDetail] = useState<MapDetail | null>(null)

  const selectedVesselId = detail?.type === 'vessel' ? detail.id : undefined

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header onMenuClick={() => setNavOpen((o) => !o)} />

      <div className="flex">
        <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />

        <main className="min-w-0 flex-1">
          <div className="mx-auto max-w-[1600px] px-3 py-4 sm:px-4 lg:px-5">
            {/* Page heading */}
            <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
              <div>
                <h1 className="text-balance text-xl font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
                  Source Reconstruction &amp; Vessel Attribution
                </h1>
                <p className="mt-0.5 font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
                  Case 24-071 · Arabian Sea · Restricted
                </p>
              </div>
              <span className="rounded-sm border border-border bg-card px-2.5 py-1 font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
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

            <footer className="mt-6 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3 pb-2">
              <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                VARUNA · Govt. of India
              </span>
              <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                Classification · Restricted · For official use only
              </span>
            </footer>
          </div>
        </main>
      </div>

      <DetailDrawer detail={detail} onClose={() => setDetail(null)} />
    </div>
  )
}
