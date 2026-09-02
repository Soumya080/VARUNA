'use client'

import { ACTIVE_CASE, OTHER_CASES, type CaseStatus } from '@/lib/mock-data'
import { SectionLabel, StatusBadge } from '@/components/primitives'
import { FileText, Plus, Search, Filter, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import Link from 'next/link'

function statusTone(status: CaseStatus) {
  switch (status) {
    case 'ACTIVE ANALYSIS': return 'saffron' as const
    case 'ANALYSIS': return 'ok' as const
    case 'REVIEW': return 'warn' as const
    default: return 'muted' as const
  }
}

const ALL_CASES = [
  { ...ACTIVE_CASE, type: 'Oil Spill', analyst: 'Analyst Rao', updated: '06:55 UTC', evidence: 96 },
  { ...OTHER_CASES[0], type: 'Oil Spill', analyst: 'Analyst Sharma', updated: '05:30 UTC', evidence: 88 },
  { ...OTHER_CASES[1], type: 'AIS Anomaly', analyst: 'Analyst Mehta', updated: '04:15 UTC', evidence: 72 },
  { ...OTHER_CASES[2], type: 'Unauthorized Entry', analyst: 'Analyst Patel', updated: '22:00 UTC', evidence: 95 },
  { id: 'CASE 24-067', region: 'Lakshadweep Sea', status: 'CLOSED' as CaseStatus, type: 'Oil Spill', analyst: 'Analyst Rao', updated: '14:20 UTC', evidence: 98 },
  { id: 'CASE 24-066', region: 'Palk Strait', status: 'CLOSED' as CaseStatus, type: 'AIS Anomaly', analyst: 'Analyst Gupta', updated: '11:00 UTC', evidence: 91 },
]

export default function CasesPage() {
  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-xl font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Case Management
          </h1>
          <p className="mt-0.5 font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
            All cases · VARUNA
          </p>
        </div>
        <button type="button" className="flex items-center gap-1.5 rounded-sm bg-saffron px-3 py-2 text-[13px] font-semibold uppercase tracking-[0.08em] text-saffron-foreground transition-colors hover:bg-saffron/90">
          <Plus className="h-3.5 w-3.5" />
          New Case
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Total Cases', value: ALL_CASES.length.toString(), tone: 'navy' },
          { label: 'Active', value: ALL_CASES.filter(c => c.status !== 'CLOSED').length.toString(), tone: 'saffron' },
          { label: 'Under Review', value: ALL_CASES.filter(c => c.status === 'REVIEW').length.toString(), tone: 'warn' },
          { label: 'Closed', value: ALL_CASES.filter(c => c.status === 'CLOSED').length.toString(), tone: 'ok' },
        ].map((s) => (
          <div key={s.label} className="rounded-sm border border-border bg-card p-3">
            <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">{s.label}</div>
            <div className="mt-1 font-mono text-[23px] font-bold text-foreground">{s.value}</div>
          </div>
        ))}
      </div>

      {/* Search + Filter */}
      <div className="mt-3 flex gap-2">
        <div className="flex flex-1 items-center gap-2 rounded-sm border border-border bg-card px-3 py-2">
          <Search className="h-4 w-4 text-muted-foreground" />
          <span className="text-[13px] text-muted-foreground">Search cases by ID, region, or type...</span>
        </div>
        <button type="button" className="flex items-center gap-1.5 rounded-sm border border-border bg-card px-3 py-2 text-[13px] text-muted-foreground hover:bg-muted">
          <Filter className="h-3.5 w-3.5" />
          Filters
        </button>
      </div>

      {/* Case listing */}
      <section className="mt-3 rounded-sm border border-border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-border">
                {['Case ID', 'Region', 'Type', 'Analyst', 'Status', 'Updated', 'Evidence', ''].map((h) => (
                  <th key={h} className="px-4 py-2.5 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ALL_CASES.map((c) => (
                <tr key={c.id} className="border-b border-border/50 last:border-b-0 hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3 font-mono text-[13px] font-semibold text-foreground">{c.id}</td>
                  <td className="px-4 py-3 text-[13px] text-foreground">{c.region}</td>
                  <td className="px-4 py-3 text-[13px] text-muted-foreground">{c.type}</td>
                  <td className="px-4 py-3 text-[13px] text-muted-foreground">{c.analyst}</td>
                  <td className="px-4 py-3">
                    <StatusBadge tone={statusTone(c.status)} dot>{c.status}</StatusBadge>
                  </td>
                  <td className="px-4 py-3 font-mono text-[12px] text-muted-foreground">{c.updated}</td>
                  <td className="px-4 py-3 font-mono text-[13px] font-medium text-foreground">{c.evidence}%</td>
                  <td className="px-4 py-3">
                    <Link href="/" className="text-saffron hover:text-saffron/80">
                      <ChevronRight className="h-4 w-4" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
