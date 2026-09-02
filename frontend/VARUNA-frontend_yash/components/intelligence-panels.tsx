'use client'

/**
 * New panels (STEP 4, Phases 6-11): CHHAYA, uncertainty, decision trace,
 * SMRITI, PRAMAN/provenance. Built from the SAME `Panel`/`Row`/`StatusBadge`
 * primitives already used throughout `case-intelligence.tsx` — no new
 * visual language, only new content sourced from
 * `OperatorCase.intelligence` (real data, from `CaseIntelligenceService` via
 * `build_product_case()` — ADR-0013).
 */
import { useOperatorCaseData } from '@/lib/operator-case-context'
import { EvidenceModeBadge } from './evidence-mode-badge'
import { InfoTip, SectionLabel, StatusBadge } from './primitives'

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2 py-0.5">
      <span className="text-[12px] text-muted-foreground">{label}</span>
      <span className="text-right font-mono text-[13px] font-medium tabular-nums text-foreground">
        {value}
      </span>
    </div>
  )
}

function Panel({
  title,
  tip,
  id,
  children,
}: {
  title: string
  tip?: string
  id?: string
  children: React.ReactNode
}) {
  return (
    <section id={id} className="scroll-mt-14 border-b border-border px-3.5 py-3 last:border-b-0">
      <div className="mb-2 flex items-center gap-1.5">
        <SectionLabel>{title}</SectionLabel>
        {tip && <InfoTip label={tip} />}
      </div>
      {children}
    </section>
  )
}

/* ------------------------------------------------------------------ */
/* CHHAYA — source hypotheses                                          */
/* ------------------------------------------------------------------ */

export function ChhayaPanel() {
  const oc = useOperatorCaseData()
  const intel = oc?.intelligence

  if (!intel || intel.status !== 'produced') {
    return (
      <Panel id="chhaya-panel" title="CHHAYA — Source Hypotheses">
        <p className="text-[12px] text-muted-foreground">
          {intel?.reason ?? 'Not composed for this case.'}
        </p>
      </Panel>
    )
  }
  const hyp = intel.hypotheses
  if (!hyp || hyp.insufficient_evidence) {
    return (
      <Panel id="chhaya-panel" title="CHHAYA — Source Hypotheses">
        <p className="text-[12px] text-muted-foreground">
          Insufficient evidence for a source hypothesis.
        </p>
      </Panel>
    )
  }

  return (
    <Panel
      id="chhaya-panel"
      title="CHHAYA — Source Hypotheses"
      tip="Declared likelihood-ratio update over stated assumptions. NOT a trained or calibrated ML model — the methodology note below is the backend's own wording."
    >
      <div className="mb-1.5 flex items-center gap-1.5">
        <StatusBadge tone="navy">{hyp.method.replace(/_/g, ' ')}</StatusBadge>
        <EvidenceModeBadge mode={hyp.envelope.mode} compact />
      </div>
      <p className="mb-2 text-[11px] italic leading-snug text-muted-foreground">
        {hyp.methodology_note}
      </p>
      <div className="space-y-1">
        {hyp.hypotheses
          .slice()
          .sort((a, b) => b.posterior - a.posterior)
          .map((h) => (
            <Row
              key={h.source_class}
              label={h.source_class.replace(/_/g, ' ')}
              value={`${(h.posterior * 100).toFixed(1)}% relative plausibility`}
            />
          ))}
      </div>
      {hyp.contradictions.length > 0 && (
        <div className="mt-2 rounded-sm border border-[color-mix(in_oklch,var(--warn)_40%,transparent)] bg-[color-mix(in_oklch,var(--warn)_8%,transparent)] px-2 py-1.5">
          <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-[color-mix(in_oklch,var(--warn)_55%,black)]">
            Contradicting evidence
          </span>
          <ul className="mt-1 list-disc pl-4 text-[11px] text-muted-foreground">
            {hyp.contradictions.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  )
}

/* ------------------------------------------------------------------ */
/* Uncertainty — component-level, never collapsed to one number        */
/* ------------------------------------------------------------------ */

const OOD_TONE: Record<string, 'ok' | 'warn' | 'destructive' | 'muted'> = {
  in_domain: 'ok',
  borderline: 'warn',
  out_of_domain: 'destructive',
  unknown: 'muted',
}

export function UncertaintyPanel() {
  const oc = useOperatorCaseData()
  const u = oc?.intelligence.uncertainty

  if (!u) {
    return (
      <Panel title="Uncertainty">
        <p className="text-[12px] text-muted-foreground">
          {oc?.intelligence.reason ?? 'Not available for this case.'}
        </p>
      </Panel>
    )
  }

  const components: Array<[string, typeof u.model_confidence]> = [
    ['Model confidence', u.model_confidence],
    ['Data quality', u.data_quality],
    ['Evidence agreement', u.evidence_agreement],
    ['Attribution uncertainty', u.attribution_uncertainty],
    ['Forecast uncertainty', u.forecast_uncertainty],
    ['Decision confidence', u.decision_confidence],
  ]

  return (
    <Panel
      title="Uncertainty"
      tip="Component-level by design — a single collapsed number would hide what the operator actually needs to know."
    >
      <div className="mb-1.5 flex items-center gap-2">
        <span className="text-[12px] text-muted-foreground">OOD risk</span>
        <StatusBadge tone={OOD_TONE[u.ood_risk] ?? 'muted'} dot>
          {u.ood_risk.replace(/_/g, ' ')}
        </StatusBadge>
        {u.evidence_conflict_count > 0 && (
          <StatusBadge tone="warn">{u.evidence_conflict_count} conflict(s)</StatusBadge>
        )}
      </div>
      {components.map(([label, m]) =>
        m ? (
          <Row
            key={label}
            label={label}
            value={m.value !== null ? `${m.value.toFixed(2)} (${m.status})` : m.status}
          />
        ) : (
          <Row key={label} label={label} value="—" />
        ),
      )}
    </Panel>
  )
}

/* ------------------------------------------------------------------ */
/* Decision trace / Next Best Action                                   */
/* ------------------------------------------------------------------ */

export function DecisionTracePanel() {
  const oc = useOperatorCaseData()
  const trace = oc?.intelligence.decision_trace
  const nba = oc?.intelligence.next_best_action

  if (!trace) {
    return (
      <Panel title="Agent Decision Trace">
        <p className="text-[12px] text-muted-foreground">
          {oc?.intelligence.reason ?? 'Not available for this case.'}
        </p>
      </Panel>
    )
  }

  return (
    <Panel
      title="Agent Decision Trace"
      tip="Why VARUNA chose its next action. Every step is a real, executed loop iteration — not a chat response."
    >
      <div className="mb-2 flex items-center gap-1.5">
        <StatusBadge tone={trace.terminal_action === 'proceed_to_decision' ? 'ok' : 'warn'}>
          {trace.terminal_action?.replace(/_/g, ' ') ?? 'in progress'}
        </StatusBadge>
        <span className="font-mono text-[11px] text-muted-foreground">
          {trace.iterations} iteration(s)
        </span>
      </div>
      {trace.terminal_reason && (
        <p className="mb-2 text-[12px] leading-snug text-foreground/90">{trace.terminal_reason}</p>
      )}
      {nba && (
        <div className="mb-2 rounded-sm border border-border bg-muted/30 px-2.5 py-2">
          <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
            Selected action
          </div>
          <div className="mt-0.5 text-[13px] font-semibold text-foreground">
            {nba.kind.replace(/_/g, ' ')}
          </div>
          <div className="mt-0.5 text-[11px] text-muted-foreground">{nba.because}</div>
        </div>
      )}
      <ol className="space-y-1">
        {trace.steps.map((step) => (
          <li key={step.iteration} className="flex items-start gap-2 text-[11px]">
            <span className="mt-0.5 font-mono text-muted-foreground">{step.iteration}.</span>
            <span className="text-foreground/90">
              <span className="font-mono uppercase tracking-[0.06em] text-muted-foreground">
                {step.phase}
              </span>{' '}
              — {step.note}
            </span>
          </li>
        ))}
      </ol>
    </Panel>
  )
}

/* ------------------------------------------------------------------ */
/* SMRITI — advisory memory                                            */
/* ------------------------------------------------------------------ */

export function SmritiPanel() {
  const oc = useOperatorCaseData()
  const hits = oc?.intelligence.memory_hits ?? []

  return (
    <Panel
      title="SMRITI — Retrieved Cases"
      tip="Structured similarity retrieval over prior cases. ADVISORY ONLY: never overrides current evidence."
    >
      <StatusBadge tone="saffron" dot className="mb-2">
        Advisory memory — not current evidence
      </StatusBadge>
      {hits.length === 0 ? (
        <p className="text-[12px] text-muted-foreground">
          {oc?.intelligence.status === 'produced'
            ? 'No similar prior cases found.'
            : (oc?.intelligence.reason ?? 'Not available for this case.')}
        </p>
      ) : (
        <div className="space-y-1.5">
          {hits.map((h) => (
            <div key={h.case_id} className="rounded-sm border border-border bg-muted/20 px-2 py-1.5">
              <div className="flex items-center justify-between">
                <span className="font-mono text-[12px] font-medium text-foreground">
                  {h.case_id}
                </span>
                <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                  score {h.score.toFixed(2)}
                </span>
              </div>
              <div className="mt-0.5 flex items-center justify-between text-[11px] text-muted-foreground">
                <span>{h.outcome ?? 'outcome unknown'}</span>
                <span className="italic">{h.provenance_source}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}

/* ------------------------------------------------------------------ */
/* Forecast — PRATIVARTAN / PRAVAAH                                     */
/* ------------------------------------------------------------------ */

export function ForecastPanel() {
  const oc = useOperatorCaseData()
  const section = oc?.forecast

  if (!section || section.status !== 'produced' || !section.value) {
    return (
      <Panel id="forecast-panel" title="Forecast — PRAVAAH">
        <p className="text-[12px] text-muted-foreground">
          {section?.reason ?? 'Forecast unavailable for this case.'}
        </p>
      </Panel>
    )
  }
  const f = section.value

  return (
    <Panel
      id="forecast-panel"
      title="Forecast — PRAVAAH"
      tip="Forward drift from the detected slick's own position, computed by the real PRAVAAH provider against the case's forcing field — not a re-derivation from the reconstructed origin."
    >
      <div className="mb-1.5 flex items-center gap-1.5">
        <EvidenceModeBadge mode={section.evidence_mode} />
        {f.envelope.case_id && (
          <span className="font-mono text-[10px] text-muted-foreground">
            case {f.envelope.case_id}
          </span>
        )}
      </div>
      <Row label="Horizon" value={`${f.horizon_hours.toFixed(1)} h`} />
      <Row label="Computed" value={new Date(f.computed_at).toISOString().slice(0, 16).replace('T', ' ')} />
      <Row label="Trajectory file" value={f.trajectory_path.split('/').pop() ?? f.trajectory_path} />

      {f.landfalls.length > 0 ? (
        <div className="mt-2 border-t border-border pt-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
            Predicted landfall
          </span>
          {f.landfalls.map((lf, i) => (
            <div key={i} className="mt-1 rounded-sm border border-border bg-muted/20 px-2 py-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[12px] font-medium text-foreground">{lf.location_name}</span>
                <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                  {(lf.probability * 100).toFixed(0)}% probability
                </span>
              </div>
              <div className="mt-0.5 text-[11px] text-muted-foreground">
                ETA {lf.hours_until.toFixed(1)}h · {lf.coastline_segment_km.toFixed(1)} km segment
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-2 text-[11px] text-muted-foreground">
          No landfall predicted within the forecast horizon.
        </p>
      )}

      {f.affected_fishing_zones.length > 0 && (
        <Row label="Fishing zones affected" value={f.affected_fishing_zones.length} />
      )}
    </Panel>
  )
}

/* ------------------------------------------------------------------ */
/* PRAMAN — provenance / audit                                         */
/* ------------------------------------------------------------------ */

export function PramanPanel() {
  const oc = useOperatorCaseData()
  if (!oc) return null
  const p = oc.provenance

  return (
    <Panel title="PRAMAN — Provenance &amp; Audit" tip="Why you can trust this result: what produced it, and what can be verified.">
      <Row label="Case ID" value={p.case_id} />
      <Row label="Artifacts" value={p.artifact_ids.length} />
      {p.artifact_ids.map((id) => (
        <div key={id} className="mt-1 truncate font-mono text-[10px] text-muted-foreground">
          {id}
        </div>
      ))}
      {Object.entries(p.model_versions).map(([stage, version]) => (
        <Row key={stage} label={stage} value={version} />
      ))}
      <Row
        label="Manifest artifact"
        value={p.manifest_artifact_id ?? '— (not yet registered by GoldenCaseWorkflow)'}
      />
      <div className="mt-2 border-t border-border pt-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
          Evidence lineage ({oc.intelligence.evidence_lineage.length} item(s))
        </span>
        <div className="mt-1 max-h-32 space-y-0.5 overflow-y-auto scroll-thin">
          {oc.intelligence.evidence_lineage.map((item) => (
            <div key={item.evidence_id} className="flex items-center justify-between text-[11px]">
              <span className="truncate text-muted-foreground">
                {item.kind} · {item.produced_by}
              </span>
              <EvidenceModeBadge mode={item.mode} compact />
            </div>
          ))}
        </div>
      </div>
    </Panel>
  )
}
