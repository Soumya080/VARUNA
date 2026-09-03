'use client'

import { CASE_NAV, CASE_NAV_ROUTES } from '@/lib/mock-data'
import { useEffect, useState } from 'react'
import { listCases, type CaseRow } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  Anchor,
  FileStack,
  GitBranch,
  LayoutGrid,
  Plus,
  Radar,
  Ship,
  Target,
  X,
} from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV_ICONS = [LayoutGrid, Radar, Target, Ship, Anchor, GitBranch]


export function Sidebar({
  open = false,
  onClose,
}: {
  open?: boolean
  onClose?: () => void
}) {
  // Real cases from the backend. The sidebar previously showed one hardcoded
  // "active case" and three fake others on buttons that did nothing.
  const [cases, setCases] = useState<CaseRow[]>([])
  useEffect(() => {
    listCases().then((r) => setCases(r.items)).catch(() => setCases([]))
  }, [])
  const active = cases[0] ?? null
  const others = cases.slice(1)

  const pathname = usePathname()

  return (
    <>
      {/* Mobile backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/50 xl:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-transform duration-200',
          'top-0 pt-14 xl:sticky xl:top-14 xl:z-0 xl:h-[calc(100vh-3.5rem)] xl:translate-x-0 xl:pt-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
        aria-label="Case navigation"
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute right-2 top-16 grid h-7 w-7 place-items-center rounded-sm text-sidebar-foreground/60 hover:bg-white/5 xl:hidden"
          aria-label="Close navigation"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="flex-1 overflow-y-auto scroll-thin px-3 py-4">
          {/* Active case — the most recently created REAL case. */}
          <div className="mb-1 px-1 font-mono text-[11px] font-medium uppercase tracking-[0.16em] text-sidebar-foreground/45">
            Active Case
          </div>
          <div className="rounded-sm border border-sidebar-border bg-sidebar-accent/60 p-3">
            {active ? (
              <>
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[15px] font-semibold tracking-wide text-primary-foreground">
                    {active.case_id}
                  </span>
                </div>
                <div className="mt-0.5 text-[13px] text-sidebar-foreground/70">
                  {active.n_alerts} alert{active.n_alerts === 1 ? '' : 's'} ·{' '}
                  {active.n_missions} mission{active.n_missions === 1 ? '' : 's'}
                </div>
                <div className="mt-2 flex items-center gap-1.5">
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="absolute inline-flex h-full w-full rounded-full bg-saffron opacity-70 animate-pulse-ring" />
                    <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-saffron" />
                  </span>
                  <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-saffron">
                    {active.status}
                  </span>
                </div>
              </>
            ) : (
              <div className="text-[12px] leading-snug text-sidebar-foreground/60">
                No case loaded yet. Run a scenario from the cockpit.
              </div>
            )}
          </div>

          {/* Case navigation */}
          <nav className="mt-5 space-y-0.5" aria-label="Case sections">
            {CASE_NAV.map((item, i) => {
              const Icon = NAV_ICONS[i] ?? LayoutGrid
              const href = CASE_NAV_ROUTES[item] ?? '/'
              const isActive = pathname === href
              return (
                <Link
                  key={item}
                  href={href}
                  onClick={onClose}
                  aria-current={isActive ? 'page' : undefined}
                  className={cn(
                    'group flex w-full items-center gap-2.5 rounded-sm px-2.5 py-2 text-left text-[14px] transition-colors',
                    isActive
                      ? 'bg-white/8 font-medium text-primary-foreground'
                      : 'text-sidebar-foreground/65 hover:bg-white/5 hover:text-sidebar-foreground',
                  )}
                >
                  <Icon
                    className={cn(
                      'h-4 w-4 shrink-0',
                      isActive ? 'text-saffron' : 'text-sidebar-foreground/45',
                    )}
                  />
                  {item}
                  {isActive && (
                    <span className="ml-auto h-1 w-1 rounded-full bg-saffron" />
                  )}
                </Link>
              )
            })}
          </nav>

          {/* Other cases — real, and they navigate. These were three
              hardcoded cases on buttons with no onClick. */}
          {others.length > 0 && (
            <>
              <div className="mb-2 mt-6 px-1 font-mono text-[11px] font-medium uppercase tracking-[0.16em] text-sidebar-foreground/45">
                Other Cases
              </div>
              <div className="space-y-1">
                {others.map((c) => (
                  <Link
                    key={c.case_id}
                    href={`/?case=${encodeURIComponent(c.case_id)}`}
                    onClick={onClose}
                    className="flex w-full items-center justify-between rounded-sm border border-transparent px-2.5 py-2 text-left transition-colors hover:border-sidebar-border hover:bg-white/5"
                  >
                    <span className="leading-tight">
                      <span className="block font-mono text-[13px] font-medium text-sidebar-foreground/85">
                        {c.case_id}
                      </span>
                      <span className="block text-[12px] text-sidebar-foreground/50">
                        {c.n_alerts} alert{c.n_alerts === 1 ? '' : 's'}
                      </span>
                    </span>
                    <span className={cn(
                      'font-mono text-[10px] font-semibold uppercase tracking-[0.08em]',
                      c.status === 'complete' ? 'text-[var(--ok)]'
                        : c.status === 'ood' ? 'text-destructive'
                        : 'text-saffron',
                    )}>
                      {c.status}
                    </span>
                  </Link>
                ))}
              </div>
            </>
          )}
        </div>

        {/* New case */}
        <div className="border-t border-sidebar-border p-3">
          <Link
            href="/cases"
            className="flex w-full items-center justify-center gap-2 rounded-sm border border-saffron/40 bg-saffron/10 px-3 py-2 text-[13px] font-semibold uppercase tracking-[0.08em] text-saffron transition-colors hover:bg-saffron/20"
          >
            <Plus className="h-3.5 w-3.5" />
            New Case
          </Link>
          <div className="mt-2 flex items-center gap-1.5 px-1">
            <FileStack className="h-3 w-3 text-sidebar-foreground/40" />
            <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-sidebar-foreground/40">
              Govt. of India · Restricted
            </span>
          </div>
        </div>
      </aside>
    </>
  )
}
