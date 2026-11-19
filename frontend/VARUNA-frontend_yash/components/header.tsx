'use client'

import { NAV_MENUS, TOP_NAV, TOP_NAV_ROUTES } from '@/lib/mock-data'
import { cn } from '@/lib/utils'
import { useAuth } from '@/lib/auth-context'
import { AuthActionError, getSystemConfigReport, type SystemConfigReport } from '@/lib/api'
import {
  AlertTriangle,
  Anchor,
  BarChart3,
  ChevronDown,
  ChevronRight,
  FileText,
  Globe,
  LayoutDashboard,
  LogOut,
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
      <div className="font-mono text-xl font-medium tabular-nums text-primary-foreground">
        {time} <span className="text-primary-foreground/50">UTC</span>
      </div>
      <div className="font-mono text-[11px] tracking-wider text-primary-foreground/55">
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
        <span className="text-[14px] font-semibold text-foreground">{navItem}</span>
      </div>

      {/* Sections */}
      <div className="max-h-[420px] overflow-y-auto scroll-thin py-1">
        {menu.sections.map((section, sIdx) => (
          <div key={sIdx}>
            {sIdx > 0 && <div className="mx-3 my-1 border-t border-border" />}
            {section.heading && (
              <div className="px-4 pt-2.5 pb-1 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
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
                    <span className="text-[13px] font-semibold text-foreground group-hover:text-saffron transition-colors">
                      {item.label}
                    </span>
                    {item.badge && (
                      <span
                        className={cn(
                          'inline-flex items-center rounded-sm border px-1.5 py-px font-mono text-[10px] font-medium uppercase tracking-[0.06em]',
                          badgeToneClasses[item.tone ?? 'muted'],
                        )}
                      >
                        {item.badge}
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-[12px] leading-snug text-muted-foreground">
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
        <div className="flex items-center gap-1.5 border-t border-border px-4 py-2 font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
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

/* ------------------------------------------------------------------ */
/* STEP 7: real login/session state, replacing the previous hardcoded    */
/* "Analyst Rao" identity. Same visual footprint (avatar + name/role     */
/* button, dropdown popover) — only the content and the mechanism are    */
/* real now.                                                             */
/* ------------------------------------------------------------------ */

const ROLE_LABEL: Record<string, string> = {
  admin: 'Administrator',
  duty_officer: 'Duty Officer',
  analyst: 'Analyst',
  field_operator: 'Field Operator',
  read_only: 'Read Only',
}

function initials(username: string): string {
  return username.slice(0, 2).toUpperCase()
}

function ProfileWidget({
  profileOpen,
  setProfileOpen,
  profileRef,
}: {
  profileOpen: boolean
  setProfileOpen: (fn: (o: boolean) => boolean) => void
  profileRef: React.RefObject<HTMLDivElement | null>
}) {
  const { session, isAuthenticated, isExpired, login, logout } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    setPending(true)
    setError(null)
    try {
      await login(username, password)
      setPassword('')
    } catch (err) {
      setError(err instanceof AuthActionError ? 'Invalid username or password.' : 'Could not reach the backend.')
    } finally {
      setPending(false)
    }
  }

  return (
    <div ref={profileRef} className="relative">
      <button
        type="button"
        onClick={() => setProfileOpen((o) => !o)}
        className="flex items-center gap-2 rounded-sm border border-white/10 py-1 pl-1 pr-1.5 transition-colors hover:bg-white/5"
        aria-haspopup="menu"
        aria-expanded={profileOpen}
      >
        <span className="grid h-7 w-7 place-items-center rounded-sm bg-saffron font-mono text-xl font-bold text-saffron-foreground">
          {isAuthenticated && session ? initials(session.username) : '—'}
        </span>
        <span className="hidden text-left leading-tight md:block">
          <span className="block text-[13px] font-medium text-primary-foreground">
            {isAuthenticated && session ? session.username : 'Not signed in'}
          </span>
          <span className="block font-mono text-[11px] text-navy-foreground/55">
            {isAuthenticated && session ? (ROLE_LABEL[session.role] ?? session.role) : 'Sign in required'}
          </span>
        </span>
        <ChevronDown className="h-3.5 w-3.5 text-navy-foreground/60" />
      </button>

      {profileOpen && (
        <div
          role="menu"
          className="nav-dropdown-enter absolute right-0 top-full z-50 mt-1 w-64 overflow-hidden rounded-sm border border-border bg-popover py-1 text-popover-foreground shadow-lg"
        >
          {isAuthenticated && session ? (
            <>
              <div className="border-b border-border px-3 py-2">
                <div className="text-[13px] font-medium">{session.username}</div>
                <div className="font-mono text-[11px] text-muted-foreground">
                  Role · {ROLE_LABEL[session.role] ?? session.role}
                </div>
              </div>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  logout()
                  setProfileOpen(() => false)
                }}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[13px] hover:bg-muted"
              >
                <LogOut className="h-3.5 w-3.5" />
                Log Out
              </button>
              <div className="mt-1 flex items-center gap-1.5 border-t border-border px-3 py-2 text-[11px] text-muted-foreground">
                <ShieldCheck className="h-3 w-3 text-[var(--ok)]" />
                Session secured · Govt. of India
              </div>
            </>
          ) : (
            <form onSubmit={handleLogin} className="p-3">
              {isExpired && (
                <p className="mb-2 text-[12px] text-destructive">Session expired. Please sign in again.</p>
              )}
              <label className="block text-[11px] font-medium uppercase tracking-[0.06em] text-muted-foreground">
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                className="mt-1 w-full rounded-sm border border-border bg-background px-2 py-1.5 text-[13px]"
              />
              <label className="mt-2 block text-[11px] font-medium uppercase tracking-[0.06em] text-muted-foreground">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                className="mt-1 w-full rounded-sm border border-border bg-background px-2 py-1.5 text-[13px]"
              />
              {error && <p className="mt-2 text-[12px] text-destructive">{error}</p>}
              <button
                type="submit"
                disabled={pending || !username || !password}
                className="mt-3 w-full rounded-sm bg-primary px-3 py-1.5 text-[12px] font-semibold uppercase tracking-[0.08em] text-primary-foreground disabled:opacity-50"
              >
                {pending ? 'Signing in…' : 'Sign In'}
              </button>
              <p className="mt-2 text-[10px] text-muted-foreground">
                Demo credentials: officer / officer-demo-pass
              </p>
            </form>
          )}
        </div>
      )}
    </div>
  )
}

export function Header({ onMenuClick }: { onMenuClick?: () => void }) {
  const pathname = usePathname()
  const [openNav, setOpenNav] = useState<string | null>(null)
  const [profileOpen, setProfileOpen] = useState(false)
  const profileRef = useRef<HTMLDivElement>(null)
  const navRef = useRef<HTMLElement>(null)

  // Phase 11 fix (docs/product/HONESTY_LEDGER.md #21): the status pill
  // used to say "Operational" unconditionally. Now reads the real
  // capability report — a demo whose header honestly says "SMTP/DB
  // NOT_CONFIGURED" is more credible than one that always claims full
  // operational status.
  const [configReport, setConfigReport] = useState<SystemConfigReport | null>(null)
  useEffect(() => {
    let cancelled = false
    getSystemConfigReport()
      .then((r) => { if (!cancelled) setConfigReport(r) })
      .catch(() => { if (!cancelled) setConfigReport(null) })
    return () => { cancelled = true }
  }, [])

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
      <div className="flex flex-wrap xl:flex-nowrap min-h-14 items-center gap-x-3 gap-y-2 px-3 sm:px-4 py-2 xl:py-0">
        {/* Left: emblem + identity */}
        <div className="flex items-center gap-3 shrink-0">
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
              <span className="font-mono text-[12px] font-semibold tracking-wide text-saffron">
                भारत
              </span>
              <span className="font-mono text-[12px] font-semibold tracking-[0.2em] text-navy-foreground/70">
                / INDIA
              </span>
            </div>
            <div className="mt-1 text-[14px] font-semibold leading-none tracking-tight text-primary-foreground">
              VARUNA
            </div>
            <div className="mt-0.5 hidden text-[11px] leading-none tracking-wide text-navy-foreground/55 sm:block">
              Environmental Evidence Reconstruction
            </div>
          </div>
        </div>

        {/* Center: navigation without dropdowns */}
        <nav ref={navRef} className="order-last xl:order-none mx-auto flex w-full xl:w-auto overflow-x-auto items-center gap-0.5 scrollbar-hide pb-1 xl:pb-0" aria-label="Primary">
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
                      'relative flex items-center gap-1.5 rounded-sm px-3 py-1.5 text-[14px] font-medium transition-colors',
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
                </div>
              </div>
            )
          })}
        </nav>

        {/* Right: clock, status, profile */}
        <div className="ml-auto flex items-center gap-3 xl:ml-0 shrink-0">
          <LiveClock />

          {(() => {
            const allReal =
              configReport &&
              configReport.auth.status === 'REAL' &&
              configReport.database.status === 'REAL' &&
              configReport.object_store.status === 'REAL'
            const color = !configReport ? 'var(--muted-foreground)' : allReal ? 'var(--ok)' : 'var(--warn)'
            const label = !configReport
              ? 'Checking…'
              : allReal
                ? 'Operational'
                : configReport.demo_mode
                  ? 'Demo mode'
                  : 'Partially configured'
            const detail = configReport
              ? [
                  `Auth: ${configReport.auth.status}`,
                  `Database: ${configReport.database.status}`,
                  `Object store: ${configReport.object_store.status}`,
                ].join(' · ')
              : undefined
            return (
              <div
                title={detail}
                className="hidden items-center gap-1.5 rounded-sm border px-2 py-1 sm:flex"
                style={{
                  borderColor: `color-mix(in oklch, ${color} 45%, transparent)`,
                  backgroundColor: `color-mix(in oklch, ${color} 16%, transparent)`,
                }}
              >
                <span className="relative flex h-2 w-2">
                  <span
                    className="absolute inline-flex h-full w-full rounded-full opacity-60 animate-pulse-ring"
                    style={{ backgroundColor: color }}
                  />
                  <span className="relative inline-flex h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
                </span>
                <span
                  className="font-mono text-[11px] font-semibold uppercase tracking-[0.1em]"
                  style={{ color: `color-mix(in oklch, ${color} 75%, white)` }}
                >
                  {label}
                </span>
              </div>
            )
          })()}

          <ProfileWidget
            profileOpen={profileOpen}
            setProfileOpen={setProfileOpen}
            profileRef={profileRef}
          />
        </div>
      </div>
    </header>
  )
}
