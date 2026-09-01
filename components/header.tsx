'use client'

import { NAV_MENUS, TOP_NAV, TOP_NAV_ROUTES } from '@/lib/mock-data'
import { cn } from '@/lib/utils'
import {
  AlertTriangle,
  Anchor,
  BarChart3,
  ChevronDown,
  ChevronRight,
  FileText,
  Globe,
  LayoutDashboard,
  Menu,
  Radar,
  ShieldCheck,
  Ship,
} from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'

const NAV_ICONS: Record<string, typeof LayoutDashboard> = {
  Dashboard: LayoutDashboard,
  Cases: FileText,
  Alerts: AlertTriangle,
  Missions: Radar,
  Assets: Ship,
  Reports: BarChart3,
  Intelligence: Globe,
}

/* ------------------------------------------------------------------ */
/* Badge tone classes — reuses the design-system token pattern          */
/* ------------------------------------------------------------------ */

const badgeToneClasses: Record<string, string> = {
  ok: 'border-[color-mix(in_oklch,var(--ok)_40%,transparent)] bg-[color-mix(in_oklch,var(--ok)_14%,transparent)] text-[color-mix(in_oklch,var(--ok)_65%,black)]',
  warn: 'border-[color-mix(in_oklch,var(--warn)_45%,transparent)] bg-[color-mix(in_oklch,var(--warn)_16%,transparent)] text-[color-mix(in_oklch,var(--warn)_60%,black)]',
  destructive:
    'border-[color-mix(in_oklch,var(--destructive)_40%,transparent)] bg-[color-mix(in_oklch,var(--destructive)_12%,transparent)] text-destructive',
  saffron:
    'border-[color-mix(in_oklch,var(--saffron)_50%,transparent)] bg-[color-mix(in_oklch,var(--saffron)_18%,transparent)] text-[color-mix(in_oklch,var(--saffron)_55%,black)]',
  muted: 'border-border bg-muted text-muted-foreground',
}

/* ------------------------------------------------------------------ */
/* Live clock widget                                                   */
/* ------------------------------------------------------------------ */

function LiveClock() {
  const [now, setNow] = useState<Date | null>(null)
  useEffect(() => {
    setNow(new Date())
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const time = now
    ? now.toLocaleTimeString('en-GB', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        timeZone: 'UTC',
      })
    : '--:--:--'
  const date = now
    ? now
        .toLocaleDateString('en-GB', {
          day: '2-digit',
          month: 'short',
          year: 'numeric',
          timeZone: 'UTC',
        })
        .toUpperCase()
    : ''

  return (
    <div className="hidden text-right leading-tight lg:block" suppressHydrationWarning>
      <div className="font-mono text-xs font-medium tabular-nums text-primary-foreground">
        {time} <span className="text-primary-foreground/50">UTC</span>
      </div>
      <div className="font-mono text-[10px] tracking-wider text-primary-foreground/55">
        {date}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Navigation dropdown menu                                            */
/* ------------------------------------------------------------------ */

function NavDropdown({
  navItem,
  onClose,
}: {
  navItem: string
  onClose: () => void
}) {
  const menu = NAV_MENUS[navItem]
  if (!menu) return null

  const Icon = NAV_ICONS[navItem] ?? LayoutDashboard

  return (
    <div
      role="menu"
      className="nav-dropdown-enter absolute left-1/2 top-full z-50 mt-1.5 w-[340px] -translate-x-1/2 overflow-hidden rounded-sm border border-border bg-popover shadow-xl shadow-black/8"
    >
      {/* Header bar */}
      <div className="flex items-center gap-2 border-b border-border bg-muted/50 px-4 py-2.5">
        <Icon className="h-4 w-4 text-saffron" />
        <span className="text-[13px] font-semibold text-foreground">{navItem}</span>
      </div>

      {/* Sections */}
      <div className="max-h-[420px] overflow-y-auto scroll-thin py-1">
        {menu.sections.map((section, sIdx) => (
          <div key={sIdx}>
            {sIdx > 0 && <div className="mx-3 my-1 border-t border-border" />}
            {section.heading && (
              <div className="px-4 pt-2.5 pb-1 font-mono text-[9px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                {section.heading}
              </div>
            )}
            {section.items.map((item) => (
              <Link
                key={item.label}
                href={item.href}
                role="menuitem"
                onClick={onClose}
                className="group flex w-full items-start gap-3 px-4 py-2 text-left transition-colors hover:bg-muted/60"
              >
                <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-saffron" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] font-semibold text-foreground group-hover:text-saffron transition-colors">
                      {item.label}
                    </span>
                    {item.badge && (
                      <span
                        className={cn(
                          'inline-flex items-center rounded-sm border px-1.5 py-px font-mono text-[9px] font-medium uppercase tracking-[0.06em]',
                          badgeToneClasses[item.tone ?? 'muted'],
                        )}
                      >
                        {item.badge}
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
                    {item.description}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        ))}
      </div>

      {/* Footer */}
      {menu.footer && (
        <div className="flex items-center gap-1.5 border-t border-border px-4 py-2 font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">
          <Anchor className="h-3 w-3 text-muted-foreground/60" />
          {menu.footer}
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Header component                                                    */
/* ------------------------------------------------------------------ */

export function Header({ onMenuClick }: { onMenuClick?: () => void }) {
  const pathname = usePathname()
  const [openNav, setOpenNav] = useState<string | null>(null)
  const [profileOpen, setProfileOpen] = useState(false)
  const profileRef = useRef<HTMLDivElement>(null)
  const navRef = useRef<HTMLElement>(null)

  // Determine which top-nav item is active based on the current pathname
  function getActiveNav(): string {
    for (const [name, route] of Object.entries(TOP_NAV_ROUTES)) {
      if (route === '/' && pathname === '/') return name
      if (route !== '/' && pathname.startsWith(route)) return name
    }
    // Sidebar routes like /detection, /source-reconstruction etc. are under "Dashboard"
    return 'Dashboard'
  }

  const active = getActiveNav()

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setProfileOpen(false)
      }
      if (navRef.current && !navRef.current.contains(e.target as Node)) {
        setOpenNav(null)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  function handleNavClick(item: string) {
    setOpenNav((prev) => (prev === item ? null : item))
  }

  return (
    <header className="sticky top-0 z-40 border-b border-[color-mix(in_oklch,var(--navy)_60%,black)] bg-navy text-navy-foreground">
      {/* Saffron / green tricolour hairline */}
      <div
        className="h-0.5 w-full"
        style={{
          background:
            'linear-gradient(90deg, var(--saffron) 0%, var(--saffron) 33%, oklch(0.97 0.01 85) 33%, oklch(0.97 0.01 85) 66%, var(--ok) 66%, var(--ok) 100%)',
        }}
        aria-hidden="true"
      />
      <div className="flex h-14 items-center gap-3 px-3 sm:px-4">
        {/* Left: emblem + identity */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onMenuClick}
            className="grid h-8 w-8 place-items-center rounded-sm border border-white/10 text-navy-foreground/80 transition-colors hover:bg-white/5 xl:hidden"
            aria-label="Toggle navigation"
          >
            <Menu className="h-4 w-4" />
          </button>

          <img
            src="/emblem/ashoka-emblem.png"
            alt="State Emblem of India"
            className="h-9 w-9 shrink-0 object-contain"
          />
          <div className="leading-none">
            <div className="flex items-baseline gap-1.5">
              <span className="font-mono text-[11px] font-semibold tracking-wide text-saffron">
                भारत
              </span>
              <span className="font-mono text-[11px] font-semibold tracking-[0.2em] text-navy-foreground/70">
                / INDIA
              </span>
            </div>
            <div className="mt-1 text-[13px] font-semibold leading-none tracking-tight text-primary-foreground">
              Maritime Intelligence System
            </div>
            <div className="mt-0.5 hidden text-[10px] leading-none tracking-wide text-navy-foreground/55 sm:block">
              Environmental Evidence Reconstruction
            </div>
          </div>
        </div>

        {/* Center: navigation with dropdowns */}
        <nav ref={navRef} className="mx-auto hidden items-center gap-0.5 xl:flex" aria-label="Primary">
          {TOP_NAV.map((item) => {
            const isActive = active === item
            const isOpen = openNav === item
            const Icon = NAV_ICONS[item] ?? LayoutDashboard
            const href = TOP_NAV_ROUTES[item] ?? '/'

            return (
              <div key={item} className="relative">
                <div className="flex items-center">
                  <Link
                    href={href}
                    onClick={() => setOpenNav(null)}
                    aria-current={isActive ? 'page' : undefined}
                    className={cn(
                      'relative flex items-center gap-1.5 rounded-l-sm pl-3 pr-1.5 py-1.5 text-[13px] font-medium transition-colors',
                      isActive
                        ? 'bg-white/8 text-primary-foreground'
                        : 'text-navy-foreground/60 hover:bg-white/5 hover:text-navy-foreground',
                    )}
                  >
                    <Icon className={cn(
                      'h-3.5 w-3.5',
                      isActive ? 'text-saffron' : 'text-navy-foreground/45',
                    )} />
                    {item}
                    {isActive && (
                      <span className="absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-saffron" />
                    )}
                  </Link>
                  <button
                    type="button"
                    onClick={() => handleNavClick(item)}
                    aria-haspopup="menu"
                    aria-expanded={isOpen}
                    className={cn(
                      'rounded-r-sm py-1.5 pr-2.5 pl-0.5 transition-colors',
                      isActive
                        ? 'bg-white/8 text-primary-foreground'
                        : 'text-navy-foreground/60 hover:bg-white/5 hover:text-navy-foreground',
                    )}
                  >
                    <ChevronDown
                      className={cn(
                        'h-3 w-3 transition-transform duration-200',
                        isOpen ? 'rotate-180 text-saffron' : 'text-navy-foreground/40',
                      )}
                    />
                  </button>
                </div>

                {isOpen && (
                  <NavDropdown navItem={item} onClose={() => setOpenNav(null)} />
                )}
              </div>
            )
          })}
        </nav>

        {/* Right: clock, status, profile */}
        <div className="ml-auto flex items-center gap-3 xl:ml-0">
          <LiveClock />

          <div className="hidden items-center gap-1.5 rounded-sm border border-[color-mix(in_oklch,var(--ok)_45%,transparent)] bg-[color-mix(in_oklch,var(--ok)_16%,transparent)] px-2 py-1 sm:flex">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-[var(--ok)] opacity-60 animate-pulse-ring" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--ok)]" />
            </span>
            <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-[color-mix(in_oklch,var(--ok)_75%,white)]">
              Operational
            </span>
          </div>

          <div ref={profileRef} className="relative">
            <button
              type="button"
              onClick={() => setProfileOpen((o) => !o)}
              className="flex items-center gap-2 rounded-sm border border-white/10 py-1 pl-1 pr-1.5 transition-colors hover:bg-white/5"
              aria-haspopup="menu"
              aria-expanded={profileOpen}
            >
              <span className="grid h-7 w-7 place-items-center rounded-sm bg-saffron font-mono text-xs font-bold text-saffron-foreground">
                RA
              </span>
              <span className="hidden text-left leading-tight md:block">
                <span className="block text-[12px] font-medium text-primary-foreground">
                  Analyst Rao
                </span>
                <span className="block font-mono text-[10px] text-navy-foreground/55">
                  Watch Officer
                </span>
              </span>
              <ChevronDown className="h-3.5 w-3.5 text-navy-foreground/60" />
            </button>

            {profileOpen && (
              <div
                role="menu"
                className="nav-dropdown-enter absolute right-0 top-full z-50 mt-1 w-52 overflow-hidden rounded-sm border border-border bg-popover py-1 text-popover-foreground shadow-lg"
              >
                <div className="border-b border-border px-3 py-2">
                  <div className="text-[12px] font-medium">Analyst Rao</div>
                  <div className="font-mono text-[10px] text-muted-foreground">
                    ID · MIS-4471 · Clearance L3
                  </div>
                </div>
                {['My Watchlist', 'Audit Log', 'Preferences'].map((i) => (
                  <button
                    key={i}
                    role="menuitem"
                    className="block w-full px-3 py-1.5 text-left text-[12px] hover:bg-muted"
                  >
                    {i}
                  </button>
                ))}
                <div className="mt-1 flex items-center gap-1.5 border-t border-border px-3 py-2 text-[10px] text-muted-foreground">
                  <ShieldCheck className="h-3 w-3 text-[var(--ok)]" />
                  Session secured · Govt. of India
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  )
}
