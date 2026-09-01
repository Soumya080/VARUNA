'use client'

import { SectionLabel, StatusBadge } from '@/components/primitives'
import { FileText, Download, Clock, User, Filter, Plus } from 'lucide-react'
import { cn } from '@/lib/utils'

const REPORTS = [
  { id: 'RPT-071-001', title: 'Case 24-071 — Preliminary Assessment', type: 'Case Report', author: 'Analyst Rao', date: '12 JUN 2024', status: 'Draft' },
  { id: 'RPT-070-002', title: 'Gulf of Kutch Oil Spill — SITREP #2', type: 'SITREP', author: 'Analyst Sharma', date: '11 JUN 2024', status: 'Submitted' },
  { id: 'RPT-069-001', title: 'Bay of Bengal AIS Anomaly Report', type: 'Case Report', author: 'Analyst Mehta', date: '10 JUN 2024', status: 'Submitted' },
  { id: 'RPT-070-001', title: 'Gulf of Kutch Oil Spill — SITREP #1', type: 'SITREP', author: 'Analyst Sharma', date: '10 JUN 2024', status: 'Submitted' },
  { id: 'RPT-068-001', title: 'EEZ Incursion — Full Investigation', type: 'Case Report', author: 'Analyst Patel', date: '08 JUN 2024', status: 'Approved' },
  { id: 'RPT-PIR-003', title: 'MARPOL Annex I Violation — Incident Report', type: 'Pollution Report', author: 'Analyst Rao', date: '05 JUN 2024', status: 'Approved' },
  { id: 'RPT-067-001', title: 'Lakshadweep Sea Discharge — Final Report', type: 'Case Report', author: 'Analyst Rao', date: '01 JUN 2024', status: 'Approved' },
]

const TEMPLATES = [
  { name: 'Case Investigation Report', description: 'Full evidence-chain case summary with attribution analysis and recommendation.', fields: 12 },
  { name: 'Situation Report (SITREP)', description: 'Periodic operational summary for command briefing. Time-stamped event log.', fields: 8 },
  { name: 'Pollution Incident Report', description: 'MARPOL-compliant documentation for environmental violation incidents.', fields: 15 },
  { name: 'Mission After-Action Report', description: 'Post-mission debrief with outcomes, findings, and lessons learned.', fields: 10 },
]

function statusTone(s: string) {
  if (s === 'Draft') return 'warn' as const
  if (s === 'Submitted') return 'saffron' as const
  if (s === 'Approved') return 'ok' as const
  return 'muted' as const
}

export default function ReportsPage() {
  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-lg font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Report Center
          </h1>
          <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
            Reports & documentation · Maritime Intelligence System
          </p>
        </div>
        <button type="button" className="flex items-center gap-1.5 rounded-sm bg-primary px-3 py-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-primary-foreground transition-colors hover:bg-[var(--navy-muted)]">
          <Plus className="h-3.5 w-3.5" />
          New Report
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Total Reports', value: REPORTS.length.toString() },
          { label: 'Drafts', value: REPORTS.filter(r => r.status === 'Draft').length.toString() },
          { label: 'Submitted', value: REPORTS.filter(r => r.status === 'Submitted').length.toString() },
          { label: 'Approved', value: REPORTS.filter(r => r.status === 'Approved').length.toString() },
        ].map(s => (
          <div key={s.label} className="rounded-sm border border-border bg-card p-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">{s.label}</div>
            <div className="mt-1 font-mono text-[22px] font-bold text-foreground">{s.value}</div>
          </div>
        ))}
      </div>

      {/* Report templates */}
      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <SectionLabel>Report Templates</SectionLabel>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {TEMPLATES.map(t => (
            <button key={t.name} type="button" className="group rounded-sm border border-border bg-background/50 p-3 text-left transition-colors hover:border-saffron/30 hover:bg-saffron/5">
              <div className="flex items-center gap-2 mb-1.5">
                <FileText className="h-4 w-4 text-saffron" />
                <span className="text-[12px] font-semibold text-foreground group-hover:text-saffron transition-colors">{t.name}</span>
              </div>
              <p className="text-[11px] leading-snug text-muted-foreground">{t.description}</p>
              <div className="mt-2 font-mono text-[9px] text-muted-foreground">{t.fields} fields</div>
            </button>
          ))}
        </div>
      </section>

      {/* Reports table */}
      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <div className="flex items-center justify-between mb-3">
          <SectionLabel>All Reports</SectionLabel>
          <button type="button" className="flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground">
            <Filter className="h-3 w-3" /> Filter
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-border">
                {['ID', 'Title', 'Type', 'Author', 'Date', 'Status', ''].map(h => (
                  <th key={h} className="pb-2 pr-4 font-mono text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {REPORTS.map(r => (
                <tr key={r.id} className="border-b border-border/50 last:border-b-0 hover:bg-muted/30 transition-colors">
                  <td className="py-2.5 pr-4 font-mono text-[10px] text-muted-foreground">{r.id}</td>
                  <td className="py-2.5 pr-4 text-[12px] font-medium text-foreground max-w-[300px] truncate">{r.title}</td>
                  <td className="py-2.5 pr-4 text-[12px] text-muted-foreground whitespace-nowrap">{r.type}</td>
                  <td className="py-2.5 pr-4 text-[12px] text-muted-foreground">{r.author}</td>
                  <td className="py-2.5 pr-4 font-mono text-[11px] text-muted-foreground whitespace-nowrap">{r.date}</td>
                  <td className="py-2.5 pr-4"><StatusBadge tone={statusTone(r.status)}>{r.status}</StatusBadge></td>
                  <td className="py-2.5"><button type="button" className="text-muted-foreground hover:text-foreground"><Download className="h-3.5 w-3.5" /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
