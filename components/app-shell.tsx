'use client'

import { useState } from 'react'
import { DetailDrawer } from './detail-drawer'
import { Header } from './header'
import type { MapDetail } from './map/map-utils'
import { Sidebar } from './sidebar'

export function AppShell({ children }: { children: React.ReactNode }) {
  const [navOpen, setNavOpen] = useState(false)
  const [detail, setDetail] = useState<MapDetail | null>(null)

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header onMenuClick={() => setNavOpen((o) => !o)} />

      <div className="flex">
        <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />

        <main className="min-w-0 flex-1">
          <div className="mx-auto max-w-[1600px] px-3 py-4 sm:px-4 lg:px-5">
            {children}

            <footer className="mt-6 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3 pb-2">
              <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                Maritime Intelligence System · Govt. of India
              </span>
              <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
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
