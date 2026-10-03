'use client'

import { useState } from 'react'
import { Header } from './header'
import { Sidebar } from './sidebar'

/**
 * DetailDrawer was mounted here with a `detail` state that nothing ever set —
 * a permanently-null drawer. Removed along with the orphaned dashboard.tsx
 * that was the only consumer of the old static-image map.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [navOpen, setNavOpen] = useState(false)

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header onMenuClick={() => setNavOpen((o) => !o)} />

      <div className="flex">
        <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />

        <main className="min-w-0 flex-1">
          <div className="mx-auto max-w-[1600px] px-3 py-4 sm:px-4 lg:px-5">
            {children}

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

    </div>
  )
}
