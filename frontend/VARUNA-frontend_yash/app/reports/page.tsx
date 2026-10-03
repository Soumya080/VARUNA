'use client'

/**
 * Phase 9 (docs/product/HONESTY_LEDGER.md #26): converted from a fully
 * fabricated "Report Center" (fake analyst names, a fake report list with
 * fake statuses, fake report templates, a "New Report" button that did
 * nothing) to real capability. VARUNA has exactly one real report
 * mechanism — `GET /v1/cases/{id}/report`, a real PDF built from the
 * composed case's own evidence (already used on the cockpit via
 * `downloadReport()`). This page is the honest home for that: pick a real
 * case, download its real report, see its real PRAMAN artifact inventory.
 * No report list is shown because VARUNA does not persist a history of
 * generated reports anywhere — each download is a fresh, real build.
 */
import { useEffect, useState } from 'react'
import { SectionLabel, StatusBadge } from '@/components/primitives'
import { PramanPanel } from '@/components/intelligence-panels'
import { OperatorCaseProvider, useOperatorCaseData } from '@/lib/operator-case-context'
import { OperatorCaseBoundary } from '@/components/operator-case-boundary'
import { listReplayFixtures, downloadReport, ApiError } from '@/lib/api'
import { FileDown, Database } from 'lucide-react'

function ReportsHeader({
  fixtures,
  fixture,
  onSelect,
}: {
  fixtures: string[]
  fixture: string
  onSelect: (f: string) => void
}) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
      <div>
        <h1 className="text-balance text-xl font-semibold leading-tight tracking-tight text-foreground sm:text-xl">
          Reports
        </h1>
        <p className="mt-0.5 font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
          Real PDF incident reports, built fresh from each case's own evidence
        </p>
      </div>
      <select
        value={fixture}
        onChange={(e) => onSelect(e.target.value)}
        className="rounded-sm border border-border bg-background px-2 py-1.5 font-mono text-[12px] text-foreground"
      >
        {fixtures.map((f) => (
          <option key={f} value={f}>
            {f}
          </option>
        ))}
      </select>
    </div>
  )
}

function DownloadReportCard({ fixture }: { fixture: string }) {
  const oc = useOperatorCaseData()
  const [downloading, setDownloading] = useState(false)
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null)

  async function handleDownload() {
    if (!oc) return
    setDownloading(true)
    setMsg(null)
    try {
      await downloadReport(oc.case_id)
      setMsg({ text: 'Report downloaded.', ok: true })
    } catch (e) {
      setMsg({
        text: e instanceof ApiError ? `Report unavailable — ${e.message}` : 'Report failed.',
        ok: false,
      })
    } finally {
      setDownloading(false)
    }
  }

  return (
    <section className="rounded-sm border border-border bg-card p-4">
      <SectionLabel>Incident Report (PDF)</SectionLabel>
      {oc ? (
        <>
          <p className="mt-2 text-[13px] text-muted-foreground">
            Case <span className="font-mono text-foreground">{oc.case_id}</span> — real detection,
            attribution, validity, mission and PRAMAN provenance sections, composed at request time
            from this case's actual evidence. Not a template fill-in.
          </p>
          <button
            type="button"
            disabled={downloading}
            onClick={handleDownload}
            className="mt-3 flex items-center gap-1.5 rounded-sm bg-primary px-3 py-2 text-[13px] font-semibold uppercase tracking-[0.08em] text-primary-foreground transition-colors hover:bg-[var(--navy-muted)] disabled:opacity-40"
          >
            <FileDown className="h-3.5 w-3.5" />
            {downloading ? 'Generating…' : `Download report — ${fixture}`}
          </button>
          {msg && (
            <p className={`mt-2 text-[12px] ${msg.ok ? 'text-[var(--ok)]' : 'text-destructive'}`}>{msg.text}</p>
          )}
        </>
      ) : (
        <p className="mt-2 text-[13px] text-muted-foreground">Loading case…</p>
      )}
    </section>
  )
}

function ArtifactInventory() {
  const oc = useOperatorCaseData()
  if (!oc) return null
  return (
    <section className="mt-3 rounded-sm border border-border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <Database className="h-4 w-4 text-teal" />
        <SectionLabel>Artifact Inventory</SectionLabel>
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
          <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">Recommendation</div>
          <div className="mt-0.5">
            <StatusBadge tone={oc.recommendation === 'valid' ? 'ok' : oc.recommendation === 'restricted' ? 'destructive' : 'muted'}>
              {oc.recommendation}
            </StatusBadge>
          </div>
        </div>
      </div>
      {oc.provenance.model_versions && Object.keys(oc.provenance.model_versions).length > 0 && (
        <div className="mt-3 space-y-0.5 border-t border-border pt-2">
          {Object.entries(oc.provenance.model_versions).map(([k, v]) => (
            <div key={k} className="flex items-center justify-between text-[12px]">
              <span className="text-muted-foreground">{k}</span>
              <span className="font-mono text-foreground">{String(v)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

export default function ReportsPage() {
  const [fixtures, setFixtures] = useState<string[]>([])
  const [fixture, setFixture] = useState<string>('IND-CASE-01')

  useEffect(() => {
    listReplayFixtures()
      .then((r) => setFixtures(r.fixtures))
      .catch(() => setFixtures([fixture]))
  }, [])

  return (
    <OperatorCaseProvider fixtureName={fixture}>
      <ReportsHeader fixtures={fixtures.length ? fixtures : [fixture]} fixture={fixture} onSelect={setFixture} />
      <OperatorCaseBoundary>
        <DownloadReportCard fixture={fixture} />
        <ArtifactInventory />
        <div className="mt-3">
          <PramanPanel />
        </div>
      </OperatorCaseBoundary>
    </OperatorCaseProvider>
  )
}
