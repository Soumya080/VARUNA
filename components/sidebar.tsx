'use client'

import { ACTIVE_CASE, CASE_NAV, CASE_NAV_ROUTES, OTHER_CASES, type CaseStatus } from '@/lib/mock-data'
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

function statusTint(status: CaseStatus) {
  switch (status) {
    case 'ACTIVE ANALYSIS':
      return 'text-saffron'
    case 'ANALYSIS':
      return 'text-teal'
    case 'REVIEW':
      return 'text-[var(--warn)]'
    default:
      return 'text-sidebar-foreground/45'
  }
}

export function Sidebar({
  open = false,
  onClose,
}: {
  open?: boolean
  onClose?: () => void
}) {
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
          {/* Active case */}
          <div className="mb-1 px-1 font-mono text-[10px] font-medium uppercase tracking-[0.16em] text-sidebar-foreground/45">
            Active Case
          </div>
          <div className="rounded-sm border border-sidebar-border bg-sidebar-accent/60 p-3">
            <div className="flex items-center justify-between">
              <span className="font-mono text-sm font-semibold tracking-wide text-primary-foreground">
                {ACTIVE_CASE.id}
              </span>
            </div>
            <div className="mt-0.5 text-[12px] text-sidebar-foreground/70">
              {ACTIVE_CASE.region}
            </div>
            <div className="mt-2 flex items-center gap-1.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full rounded-full bg-saffron opacity-70 animate-pulse-ring" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-saffron" />
              </span>
              <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-saffron">
                {ACTIVE_CASE.status}
              </span>
            </div>
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
                    'group flex w-full items-center gap-2.5 rounded-sm px-2.5 py-2 text-left text-[13px] transition-colors',
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

          {/* Other cases */}
          <div className="mb-2 mt-6 px-1 font-mono text-[10px] font-medium uppercase tracking-[0.16em] text-sidebar-foreground/45">
            Other Cases
          </div>
          <div className="space-y-1">
            {OTHER_CASES.map((c) => (
              <button
                key={c.id}
                type="button"
                className="flex w-full items-center justify-between rounded-sm border border-transparent px-2.5 py-2 text-left transition-colors hover:border-sidebar-border hover:bg-white/5"
              >
                <span className="leading-tight">
                  <span className="block font-mono text-[12px] font-medium text-sidebar-foreground/85">
                    {c.id}
                  </span>
                  <span className="block text-[11px] text-sidebar-foreground/50">
                    {c.region}
                  </span>
                </span>
                <span
                  className={cn(
                    'font-mono text-[9px] font-semibold uppercase tracking-[0.08em]',
                    statusTint(c.status),
                  )}
                >
                  {c.status}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* New case */}
        <div className="border-t border-sidebar-border p-3">
          <Link
            href="/cases"
            className="flex w-full items-center justify-center gap-2 rounded-sm border border-saffron/40 bg-saffron/10 px-3 py-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-saffron transition-colors hover:bg-saffron/20"
          >
            <Plus className="h-3.5 w-3.5" />
            New Case
          </Link>
          <div className="mt-2 flex items-center gap-1.5 px-1">
            <FileStack className="h-3 w-3 text-sidebar-foreground/40" />
            <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-sidebar-foreground/40">
              Govt. of India · Restricted
            </span>
          </div>
        </div>
      </aside>
    </>
  )
}
