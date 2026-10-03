'use client'

/**
 * Phase 9 (docs/product/HONESTY_LEDGER.md #26): converted from a fully
 * fabricated "Intelligence Fusion Center" (fake OSINT feed items, a fake
 * vessel watchlist, fake pattern-analysis counts, a fake "23 feeds active"
 * / "Live Feed" indicator) into the dedicated home for VARUNA's real
 * source-hypothesis, uncertainty, decision-trace, and SMRITI-memory
 * output — 4 of the 6 real panels from `components/intelligence-panels.tsx`
 * that this page-conversion plan called for. `ChhayaPanel` (full CHHAYA-H)
 * lives here rather than on the cockpit, where only its compact summary
 * appears in `EvidencePanels`.
 */
import { StatusBadge } from '@/components/primitives'
import {
  ChhayaPanel,
  UncertaintyPanel,
  DecisionTracePanel,
  SmritiPanel,
} from '@/components/intelligence-panels'
import { OperatorCaseProvider, useOperatorCaseData } from '@/lib/operator-case-context'
import { OperatorCaseBoundary } from '@/components/operator-case-boundary'
import { Brain } from 'lucide-react'

const DEFAULT_FIXTURE = 'IND-CASE-01'

function IntelligenceHeader() {
  const oc = useOperatorCaseData()
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
      <div>
        <h1 className="text-balance text-xl font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
          Intelligence
        </h1>
        <p className="mt-0.5 font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
          {oc?.case_id ?? DEFAULT_FIXTURE} · Source hypothesis, uncertainty, decision trace, memory
        </p>
      </div>
      <div className="flex items-center gap-1.5">
        <Brain className="h-4 w-4 text-muted-foreground" />
        <StatusBadge tone={oc ? 'ok' : 'muted'} dot>
          {oc ? 'case loaded' : 'loading'}
        </StatusBadge>
      </div>
    </div>
  )
}

function IntelligenceBody() {
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      <div className="space-y-3">
        <ChhayaPanel />
        <UncertaintyPanel />
      </div>
      <div className="space-y-3">
        <DecisionTracePanel />
        <SmritiPanel />
      </div>
    </div>
  )
}

export default function IntelligencePage() {
  return (
    <OperatorCaseProvider fixtureName={DEFAULT_FIXTURE}>
      <OperatorCaseBoundary>
        <IntelligenceHeader />
        <IntelligenceBody />
      </OperatorCaseBoundary>
    </OperatorCaseProvider>
  )
}
