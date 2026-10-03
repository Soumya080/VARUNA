'use client'

/**
 * Verification Ledger — Phase 6B (docs/product/HONESTY_LEDGER.md #19).
 *
 * The uncomfortable finding this answers: `InvestigationState.VERIFIED`
 * (varuna_contracts) is the only real "verified" value in the codebase and
 * has ZERO production call sites — nothing in the replay pipeline
 * physically verifies anything, so there is no honest way to wire it as a
 * single badge without inventing a producer for it.
 *
 * Decision (see docs/adr — new ADR for this): map "verified" onto the FIVE
 * real confirmation signals that already exist, each with an actual
 * producer, rather than fabricate a sixth. This is more defensible than a
 * single badge, not less — "what does verified mean here?" gets a
 * decomposable answer instead of a shrug.
 *
 *   Axis                 | Real producer
 *   --------------------- | -----------------------------------------------
 *   Physical confirmation | MissionRecord.state reaching CONTACT -> CONFIRMED
 *   Human authorization   | MissionRecord.human_approved_by — ASSIGNED
 *                            requires it; an enforced gate, not a
 *                            display convention
 *                            (Phase 9 fix: this axis was silently always
 *                            reporting unconfirmed — the type this file
 *                            read against declared the wrong field name,
 *                            `approved_by`, which never existed on the
 *                            wire; see lib/operator-case-types.ts)
 *   Evidence gate         | ValidityGateResult.state in {valid, degraded}
 *                            (allows_operational_action — a Python
 *                            @property, deliberately not serialised; see
 *                            ValidityGateResultValue's own note)
 *   Operator action       | AlertLifecycleRecord.status in
 *                            {acknowledged, resolved}, actor from its
 *                            own transitions
 *   Historical outcome    | SMRITI CaseMemory.outcome for THIS case
 *                            (GET /v1/cases/{id}/memory-outcome)
 *
 * Unmet axes render NOT_YET, never blank — an axis with no evidence yet is
 * a real, honest state, not an error.
 */
import { useEffect, useState } from 'react'
import { getCaseAlerts, getCaseMemoryOutcome } from '@/lib/api'
import type { OperatorCase } from '@/lib/operator-case-types'
import { InfoTip, StatusBadge } from '@/components/primitives'

interface Axis {
  id: string
  label: string
  confirmed: boolean
  detail: string
  tip: string
}

function evaluateAxes(
  oc: OperatorCase,
  alerts: { status: string; transitions: Array<{ to: string; actor: string }> }[] | null,
  memory: { recorded: boolean; outcome: string | null } | null,
): Axis[] {
  const missions = oc.mission.status === 'produced' ? oc.mission.value ?? [] : []
  const confirmedMission = missions.find((m) => m.state === 'confirmed' || m.state === 'complete')
  const approvedMission = missions.find((m) => m.human_approved_by)

  const validityState = oc.validity.status === 'produced' ? oc.validity.value?.state : null
  const allowsAction = validityState === 'valid' || validityState === 'degraded'

  const ackAlert = (alerts ?? []).find((a) => a.status === 'acknowledged' || a.status === 'resolved')
  const ackActor = ackAlert?.transitions.find((t) => t.to === 'acknowledged' || t.to === 'resolved')?.actor

  return [
    {
      id: 'physical',
      label: 'Physical confirmation',
      confirmed: Boolean(confirmedMission),
      detail: confirmedMission
        ? `mission ${confirmedMission.mission_id} reached ${confirmedMission.state}`
        : 'no mission has reached CONTACT -> CONFIRMED yet',
      tip: 'MissionState reaching CONFIRMED — the asset physically found and confirmed the contact.',
    },
    {
      id: 'authorization',
      label: 'Human authorization',
      confirmed: Boolean(approvedMission),
      detail: approvedMission
        ? `approved by ${approvedMission.human_approved_by} (mission ${approvedMission.mission_id})`
        : 'no mission has a recorded human approver',
      tip: 'MissionRecord.human_approved_by — a real, named person authorized this mission. Server-enforced: ASSIGNED cannot be reached without it.',
    },
    {
      id: 'evidence_gate',
      label: 'Evidence gate',
      confirmed: allowsAction,
      detail: validityState
        ? `validity gate: ${validityState}${allowsAction ? ' (allows operational action)' : ' (does not allow operational action)'}`
        : 'validity gate not yet evaluated',
      tip: "ValidityGateResult.state in {valid, degraded} — VARUNA's own gate between analysis and any operational action.",
    },
    {
      id: 'operator_action',
      label: 'Operator action',
      confirmed: Boolean(ackAlert),
      detail: ackAlert
        ? `alert ${ackAlert.status}${ackActor ? ` by ${ackActor}` : ''}`
        : 'no alert on this case has been acknowledged or resolved',
      tip: 'AlertLifecycleRecord.status reaching acknowledged/resolved — a real named recipient acted on a real alert.',
    },
    {
      id: 'historical',
      label: 'Historical outcome',
      confirmed: Boolean(memory?.recorded && memory.outcome),
      detail:
        memory?.recorded && memory.outcome
          ? `SMRITI recorded outcome: ${memory.outcome}`
          : 'no outcome recorded in SMRITI for this case yet',
      tip: "SMRITI CaseMemory.outcome for THIS case's own record — distinct from similar-case memory hits elsewhere in the cockpit.",
    },
  ]
}

export function VerificationLedger({ oc }: { oc: OperatorCase }) {
  const [alerts, setAlerts] = useState<
    Array<{ status: string; transitions: Array<{ to: string; actor: string }> }> | null
  >(null)
  const [memory, setMemory] = useState<{ recorded: boolean; outcome: string | null } | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setErr(null)
    Promise.all([getCaseAlerts(oc.case_id), getCaseMemoryOutcome(oc.case_id)])
      .then(([a, m]) => {
        if (cancelled) return
        setAlerts(a.items)
        setMemory(m)
      })
      .catch((e) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : 'Failed to load verification data')
      })
    return () => {
      cancelled = true
    }
  }, [oc.case_id])

  if (err) {
    return <p className="text-[11px] text-destructive">{err}</p>
  }
  if (alerts === null || memory === null) {
    return <p className="text-[11px] text-muted-foreground">Loading verification state…</p>
  }

  const axes = evaluateAxes(oc, alerts, memory)
  const nConfirmed = axes.filter((a) => a.confirmed).length

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5">
        <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-foreground">
          Verification: {nConfirmed} of {axes.length} axes confirmed
        </span>
        <InfoTip label="No single 'VERIFIED' status exists in this pipeline — nothing in the replay path physically verifies a case end to end. These five axes are the real, independently-producible confirmation signals VARUNA actually has, decomposed rather than collapsed into one badge." />
      </div>
      <ul className="space-y-1">
        {axes.map((axis) => (
          <li
            key={axis.id}
            className="flex items-start gap-2 rounded-sm border border-border bg-background/40 px-2 py-1.5 text-[11px]"
          >
            <StatusBadge tone={axis.confirmed ? 'ok' : 'muted'}>
              {axis.confirmed ? 'confirmed' : 'not_yet'}
            </StatusBadge>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1">
                <span className="font-semibold text-foreground">{axis.label}</span>
                <InfoTip label={axis.tip} />
              </div>
              <p className="truncate text-muted-foreground">{axis.detail}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
