'use client'

/**
 * Phase 9 (docs/product/HONESTY_LEDGER.md #26) — the "honesty showcase"
 * page. The mock version fabricated 3+ vessel candidates with fake
 * attribution scores, positions, and "analysis notes". The real
 * `oc.attribution` for these cases is honestly `INCONCLUSIVE` with zero
 * scored candidates (M1+M2 fix, Phase 2) — no AIS coverage was ingested,
 * so nothing was ever computed to rank. The real, publicly-documented
 * vessel identity (`historical_reconstruction`) is shown in a clearly
 * demoted, dashed-border block with NO score, exactly because it is a
 * historical record VARUNA did not compute, not a candidate it ranked.
 */
import { SectionLabel, StatusBadge, Meter, InfoTip } from '@/components/primitives'
import { Row } from '@/components/cockpit/cockpit-panels'
import { OperatorCaseProvider, useOperatorCaseData } from '@/lib/operator-case-context'
import { OperatorCaseBoundary } from '@/components/operator-case-boundary'
import { EvidenceModeBadge } from '@/components/evidence-mode-badge'
import { Ship, ScrollText } from 'lucide-react'

const DEFAULT_FIXTURE = 'IND-CASE-01'

const DECISION_TONE: Record<string, 'ok' | 'warn' | 'destructive' | 'muted'> = {
  strong_lead: 'ok',
  weak_lead: 'warn',
  not_distinguishable: 'warn',
  latent_source: 'muted',
  inconclusive: 'muted',
}

function VesselAttributionBody() {
  const oc = useOperatorCaseData()
  if (!oc) return null
  const attr = oc.attribution

  return (
    <>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-balance text-xl font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
            Vessel Attribution
          </h1>
          <p className="mt-0.5 font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
            {oc.case_id} · NYAYA attribution
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <EvidenceModeBadge mode={attr.evidence_mode} />
          <StatusBadge tone={attr.status === 'produced' ? 'ok' : 'muted'} dot>
            {attr.status.replace(/_/g, ' ')}
          </StatusBadge>
        </div>
      </div>

      {attr.status !== 'produced' || !attr.value ? (
        <section className="rounded-sm border border-border bg-card p-4">
          <p className="text-[13px] text-muted-foreground">
            {attr.reason ?? 'No attribution has been produced for this case.'}
          </p>
        </section>
      ) : (
        <>
          <section className="rounded-sm border border-border bg-card p-4">
            <SectionLabel>Computed Attribution</SectionLabel>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <StatusBadge tone={DECISION_TONE[attr.value.decision_state] ?? 'muted'} dot>
                {attr.value.decision_state.replace(/_/g, ' ')}
              </StatusBadge>
              <span className="font-mono text-[12px] text-muted-foreground">
                {attr.value.candidates.length} candidate(s) scored
              </span>
            </div>
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-[13px] text-muted-foreground">Top posterior</span>
                  <span className="font-mono text-[13px] font-medium text-foreground">
                    {(attr.value.top_posterior * 100).toFixed(1)}%
                  </span>
                </div>
                <Meter value={attr.value.top_posterior * 100} tone="teal" />
              </div>
              <div>
                <div className="mb-1 flex items-center gap-1">
                  <span className="text-[13px] text-muted-foreground">Distinguishability</span>
                  <InfoTip label="How separated the top candidates are, not how confident the top one is — a sharply-peaked posterior can still fail to distinguish two vessels in the same Phi lobe." />
                </div>
                <Meter value={attr.value.distinguishability * 100} tone="saffron" />
              </div>
            </div>
            <p className="mt-3 text-[12px] leading-snug text-muted-foreground">
              Latent finding: <strong className="text-foreground">{attr.value.latent_finding.replace(/_/g, ' ')}</strong>{' '}
              (latent probability {(attr.value.latent_probability * 100).toFixed(0)}%) — the source may be a vessel
              VARUNA has no AIS coverage for, not necessarily "no source".
            </p>
          </section>

          {attr.value.candidates.length > 0 ? (
            <section className="mt-3 rounded-sm border border-border bg-card p-4">
              <SectionLabel>Scored Candidates</SectionLabel>
              <div className="mt-2 space-y-2">
                {attr.value.candidates.map((c) => (
                  <div key={c.mmsi} className="rounded-sm border border-border bg-background/50 p-3">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[13px] font-semibold text-foreground">#{c.rank} · MMSI {c.mmsi}</span>
                      <span className="font-mono text-[13px] font-bold text-foreground">
                        {(c.posterior * 100).toFixed(1)}%
                      </span>
                    </div>
                    <Meter value={c.posterior * 100} tone={c.rank === 1 ? 'saffron' : 'muted'} />
                  </div>
                ))}
              </div>
            </section>
          ) : (
            <section className="mt-3 rounded-sm border border-border bg-card p-4">
              <div className="flex items-center gap-2">
                <Ship className="h-4 w-4 text-muted-foreground" />
                <SectionLabel>Scored Candidates</SectionLabel>
              </div>
              <p className="mt-2 text-[13px] text-muted-foreground">
                Zero candidates were scored — no AIS tracks were ingested for this case, so
                there is nothing for NYAYA to rank against the reconstructed origin. This is
                the honest computed result, not a placeholder.
              </p>
            </section>
          )}

          {attr.value.historical_reconstruction && (
            <section className="mt-3 rounded-sm border border-dashed border-border bg-muted/20 p-4">
              <div className="mb-2 flex items-center gap-2">
                <ScrollText className="h-4 w-4 text-muted-foreground" />
                <StatusBadge tone="muted">Historical record — not computed</StatusBadge>
                <InfoTip label="A real-world, publicly-documented vessel identity attached for context. This is NOT VARUNA's computed output — it carries no score, no posterior, no rank, and never contributes to the decision above." />
              </div>
              <p className="text-[15px] font-semibold text-foreground">
                {attr.value.historical_reconstruction.vessel_name}
                {attr.value.historical_reconstruction.mmsi && (
                  <span className="ml-2 font-mono text-[12px] font-normal text-muted-foreground">
                    MMSI {attr.value.historical_reconstruction.mmsi}
                  </span>
                )}
              </p>
              <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">
                {attr.value.historical_reconstruction.event_description}
              </p>
              <p className="mt-2 text-[11px] italic text-muted-foreground/80">
                {attr.value.historical_reconstruction.source_citation}
              </p>
            </section>
          )}
        </>
      )}
    </>
  )
}

export default function VesselAttributionPage() {
  return (
    <OperatorCaseProvider fixtureName={DEFAULT_FIXTURE}>
      <OperatorCaseBoundary>
        <VesselAttributionBody />
      </OperatorCaseBoundary>
    </OperatorCaseProvider>
  )
}
