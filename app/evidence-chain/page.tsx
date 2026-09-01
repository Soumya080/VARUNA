'use client'

import { EVIDENCE_HEALTH } from '@/lib/mock-data'
import { SectionLabel, StatusBadge, Meter } from '@/components/primitives'
import { EvidenceHealth } from '@/components/evidence-health'
import { Shield, FileCheck, Link2, Database, Clock, Check, Lock, Eye } from 'lucide-react'

const EVIDENCE_CHAIN = [
  { id: 'E-001', type: 'SAR Image', source: 'Sentinel-1 / ESA', acquired: '06:42 UTC', hash: 'sha256:4a7f...c2d1', integrity: 'Verified', classification: 'Restricted' },
  { id: 'E-002', type: 'AIS Track Data', source: 'VTMS / ICG', acquired: '06:20 UTC', hash: 'sha256:b3e9...1fa8', integrity: 'Verified', classification: 'Restricted' },
  { id: 'E-003', type: 'HYCOM Forcing', source: 'NCEP / NOAA', acquired: '06:00 UTC', hash: 'sha256:c1d5...8e72', integrity: 'Verified', classification: 'Unclassified' },
  { id: 'E-004', type: 'GFS Wind Field', source: 'NCEP / NOAA', acquired: '06:00 UTC', hash: 'sha256:f9a2...5b6c', integrity: 'Verified', classification: 'Unclassified' },
  { id: 'E-005', type: 'Model Output', source: 'MIS Pipeline v2.3', acquired: '06:45 UTC', hash: 'sha256:d4c7...3e91', integrity: 'Verified', classification: 'Restricted' },
  { id: 'E-006', type: 'Attribution Report', source: 'MIS Pipeline v2.3', acquired: '06:46 UTC', hash: 'sha256:a8b1...7d42', integrity: 'Verified', classification: 'Restricted' },
]

const AUDIT_LOG = [
  { time: '06:42:01 UTC', action: 'SAR image ingested', user: 'System', detail: 'Sentinel-1 IW GRD product imported' },
  { time: '06:43:15 UTC', action: 'Detection pipeline started', user: 'System', detail: 'Automated SAR classification initiated' },
  { time: '06:44:30 UTC', action: 'AIS data correlated', user: 'System', detail: '3 candidate vessels matched within AOI' },
  { time: '06:45:22 UTC', action: 'Back-trajectory complete', user: 'System', detail: '4,000 particle ensemble processed' },
  { time: '06:46:01 UTC', action: 'Attribution scores generated', user: 'System', detail: 'Spatiotemporal scoring complete' },
  { time: '06:50:00 UTC', action: 'Case opened', user: 'Analyst Rao', detail: 'Case 24-071 created from detection alert' },
  { time: '06:52:33 UTC', action: 'Evidence reviewed', user: 'Analyst Rao', detail: 'All evidence artifacts validated' },
  { time: '06:55:10 UTC', action: 'Authorization requested', user: 'Analyst Rao', detail: 'Mission assignment submitted for CO review' },
]

export default function EvidenceChainPage() {
  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-lg font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Evidence Chain
          </h1>
          <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
            Case 24-071 · Data Provenance & Integrity · Chain of Custody
          </p>
        </div>
        <StatusBadge tone="ok" dot>All Verified</StatusBadge>
      </div>

      {/* Evidence Health */}
      <section className="rounded-sm border border-border bg-card p-4">
        <div className="flex items-center gap-2 mb-3">
          <Shield className="h-4 w-4 text-[var(--ok)]" />
          <SectionLabel>Evidence Health Score</SectionLabel>
        </div>
        <EvidenceHealth />
      </section>

      {/* Evidence table */}
      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <div className="flex items-center gap-2 mb-3">
          <Link2 className="h-4 w-4 text-saffron" />
          <SectionLabel>Evidence Artifacts</SectionLabel>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-border">
                {['ID', 'Type', 'Source', 'Acquired', 'Hash', 'Integrity', 'Classification'].map((h) => (
                  <th key={h} className="pb-2 pr-4 font-mono text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {EVIDENCE_CHAIN.map((e) => (
                <tr key={e.id} className="border-b border-border/50 last:border-b-0">
                  <td className="py-2.5 pr-4 font-mono text-[11px] font-medium text-saffron">{e.id}</td>
                  <td className="py-2.5 pr-4 text-[12px] font-medium text-foreground">{e.type}</td>
                  <td className="py-2.5 pr-4 text-[12px] text-muted-foreground">{e.source}</td>
                  <td className="py-2.5 pr-4 font-mono text-[11px] text-foreground">{e.acquired}</td>
                  <td className="py-2.5 pr-4 font-mono text-[10px] text-muted-foreground">{e.hash}</td>
                  <td className="py-2.5 pr-4">
                    <StatusBadge tone="ok" dot>{e.integrity}</StatusBadge>
                  </td>
                  <td className="py-2.5">
                    <span className="inline-flex items-center gap-1 font-mono text-[10px] text-muted-foreground">
                      <Lock className="h-3 w-3" />{e.classification}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Audit Trail */}
      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <div className="flex items-center gap-2 mb-3">
          <Eye className="h-4 w-4 text-teal" />
          <SectionLabel>Audit Trail</SectionLabel>
        </div>
        <div className="relative">
          <div className="absolute left-[7px] top-3 bottom-3 w-px bg-border" />
          <div className="space-y-3">
            {AUDIT_LOG.map((item, i) => (
              <div key={i} className="flex items-start gap-3 relative">
                <span className="relative z-10 grid h-4 w-4 shrink-0 place-items-center rounded-full bg-[var(--ok)] text-white mt-0.5">
                  <Check className="h-2.5 w-2.5" />
                </span>
                <div className="flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[12px] font-medium text-foreground">{item.action}</span>
                    <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{item.time}</span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-2">
                    <span className="font-mono text-[10px] text-saffron">{item.user}</span>
                    <span className="text-[11px] text-muted-foreground">— {item.detail}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Legal admissibility */}
      <section className="mt-3 rounded-sm border border-[color-mix(in_oklch,var(--ok)_30%,transparent)] bg-[color-mix(in_oklch,var(--ok)_5%,transparent)] p-4">
        <div className="flex items-center gap-2 mb-2">
          <FileCheck className="h-4 w-4 text-[var(--ok)]" />
          <SectionLabel className="text-[color-mix(in_oklch,var(--ok)_60%,black)]">Legal Admissibility Assessment</SectionLabel>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {[
            { label: 'Data Provenance', value: 'Complete — all sources traceable', status: 'pass' },
            { label: 'Chain of Custody', value: 'Unbroken — SHA-256 hashes verified', status: 'pass' },
            { label: 'MARPOL Compliance', value: 'Evidence meets Annex I requirements', status: 'pass' },
          ].map((item) => (
            <div key={item.label} className="rounded-sm border border-border bg-card p-3">
              <div className="flex items-center gap-1.5 mb-1">
                <Check className="h-3.5 w-3.5 text-[var(--ok)]" />
                <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">{item.label}</span>
              </div>
              <span className="text-[11px] text-foreground">{item.value}</span>
            </div>
          ))}
        </div>
      </section>
    </>
  )
}
