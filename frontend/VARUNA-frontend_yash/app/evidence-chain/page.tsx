'use client'

/**
 * Phase 9 (docs/product/HONESTY_LEDGER.md #26): converted from a fully
 * fabricated page (fake SHA-256 hashes, a fake "MARPOL Compliance"
 * assessment, a fake audit trail with a fake named analyst) to real data:
 * the real evidence ledger (`oc.intelligence.evidence_lineage` — a real
 * 12-node dependency graph, shown here as a real, sortable list; the full
 * visual DAG is Phase 10), the real Verification Ledger (Phase 6B), and
 * real PRAMAN provenance. No hash is shown unless VARUNA actually computed
 * one, and no legal/regulatory compliance claim is made — VARUNA never
 * asserts MARPOL compliance anywhere in its contracts.
 */
import { SectionLabel, StatusBadge } from '@/components/primitives'
import { EvidenceHealth } from '@/components/evidence-health'
import { VerificationLedger } from '@/components/verification-ledger'
import { EvidenceDag } from '@/components/evidence-dag'
import { OperatorCaseProvider, useOperatorCaseData } from '@/lib/operator-case-context'
import { OperatorCaseBoundary } from '@/components/operator-case-boundary'
import { Shield, Link2, Database } from 'lucide-react'

const DEFAULT_FIXTURE = 'IND-CASE-01'

const KIND_TONE: Record<string, 'ok' | 'warn' | 'destructive' | 'navy' | 'saffron' | 'muted'> = {
  forcing: 'muted',
  detection: 'saffron',
  ais: 'navy',
  origin: 'navy',
  attribution: 'ok',
  source_hypothesis: 'navy',
  forecast: 'saffron',
  validity: 'ok',
  data_quality: 'warn',
  memory: 'muted',
  decision: 'ok',
  operator: 'muted',
}

function EvidenceChainBody() {
  const oc = useOperatorCaseData()
  if (!oc) return null
  const lineage = oc.intelligence.evidence_lineage ?? []
  const contradicted = lineage.filter((e) => (e.contradicts?.length ?? 0) > 0)

  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-xl font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Evidence Chain
          </h1>
          <p className="mt-0.5 font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
            {oc.case_id} · Provenance & lineage
          </p>
        </div>
        <StatusBadge tone={lineage.length > 0 ? 'ok' : 'muted'} dot>
          {lineage.length} evidence item(s)
        </StatusBadge>
      </div>

      <section className="rounded-sm border border-border bg-card p-4">
        <div className="mb-3 flex items-center gap-2">
          <Shield className="h-4 w-4 text-[var(--ok)]" />
          <SectionLabel>Evidence Health</SectionLabel>
        </div>
        <EvidenceHealth />
      </section>

      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <div className="mb-3 flex items-center gap-2">
          <Shield className="h-4 w-4 text-[var(--ok)]" />
          <SectionLabel>Verification Ledger</SectionLabel>
        </div>
        <VerificationLedger oc={oc} />
      </section>

      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <div className="mb-3 flex items-center gap-2">
          <Link2 className="h-4 w-4 text-saffron" />
          <SectionLabel>Evidence Lineage</SectionLabel>
        </div>
        <EvidenceDag lineage={lineage} />
      </section>

      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <div className="mb-3 flex items-center gap-2">
          <Link2 className="h-4 w-4 text-saffron" />
          <SectionLabel>Evidence Lineage — table view</SectionLabel>
        </div>
        {lineage.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">
            {oc.intelligence.reason ?? 'No evidence ledger entries for this case.'}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-border">
                  {['Evidence ID', 'Kind', 'Produced by', 'Summary', 'Confidence', 'Depends on'].map((h) => (
                    <th key={h} className="whitespace-nowrap pb-2 pr-4 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {lineage.map((e) => (
                  <tr key={e.evidence_id} className="border-b border-border/50 last:border-b-0">
                    <td className="py-2.5 pr-4 font-mono text-[11px] font-medium text-saffron">{e.evidence_id}</td>
                    <td className="py-2.5 pr-4">
                      <StatusBadge tone={KIND_TONE[e.kind] ?? 'muted'}>{e.kind.replace(/_/g, ' ')}</StatusBadge>
                    </td>
                    <td className="py-2.5 pr-4 font-mono text-[11px] text-muted-foreground">{e.produced_by}</td>
                    <td className="py-2.5 pr-4 text-[13px] text-foreground">{e.summary}</td>
                    <td className="py-2.5 pr-4 font-mono text-[12px] text-foreground">
                      {e.confidence != null ? `${(e.confidence * 100).toFixed(0)}%` : '—'}
                    </td>
                    <td className="py-2.5 font-mono text-[10px] text-muted-foreground">
                      {e.depends_on.length > 0 ? e.depends_on.join(', ') : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {contradicted.length > 0 && (
        <section className="mt-3 rounded-sm border border-[color-mix(in_oklch,var(--destructive)_40%,transparent)] bg-[color-mix(in_oklch,var(--destructive)_6%,transparent)] p-4">
          <SectionLabel className="text-destructive">Contradicted Evidence</SectionLabel>
          <p className="mt-1 text-[12px] text-muted-foreground">
            {contradicted.length} item(s) in this case's ledger are flagged as disagreeing with
            another item. VARUNA surfaces this rather than silently resolving it — an unresolved
            contradiction should widen uncertainty, not be hidden.
          </p>
          <ul className="mt-2 space-y-1">
            {contradicted.map((e) => (
              <li key={e.evidence_id} className="font-mono text-[11px] text-foreground">
                {e.evidence_id} contradicts: {e.contradicts?.join(', ')}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-3 rounded-sm border border-border bg-card p-4">
        <div className="mb-3 flex items-center gap-2">
          <Database className="h-4 w-4 text-teal" />
          <SectionLabel>PRAMAN Provenance</SectionLabel>
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Artifacts</div>
            <div className="mt-0.5 font-mono text-[15px] font-semibold text-foreground">
              {oc.provenance.artifact_ids?.length ?? 0}
            </div>
          </div>
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Sources</div>
            <div className="mt-0.5 font-mono text-[15px] font-semibold text-foreground">
              {oc.provenance.source_ids?.length ?? 0}
            </div>
          </div>
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Generated</div>
            <div className="mt-0.5 font-mono text-[13px] font-semibold text-foreground">
              {new Date(oc.generated_at).toISOString().slice(0, 16).replace('T', ' ')}Z
            </div>
          </div>
        </div>
      </section>
    </>
  )
}

export default function EvidenceChainPage() {
  return (
    <OperatorCaseProvider fixtureName={DEFAULT_FIXTURE}>
      <OperatorCaseBoundary>
        <EvidenceChainBody />
      </OperatorCaseBoundary>
    </OperatorCaseProvider>
  )
}
