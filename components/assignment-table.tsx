'use client'

import { ASSIGNMENTS } from '@/lib/mock-data'
import { SectionLabel, StatusBadge } from './primitives'

const priorityTone = { HIGH: 'warn', MEDIUM: 'navy', LOW: 'muted' } as const

export function AssignmentTable() {
  return (
    <section className="rounded-sm border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-3.5 py-2.5">
        <SectionLabel>Assignment &amp; Mission</SectionLabel>
        <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">
          {ASSIGNMENTS.length} tasks · pending authorization
        </span>
      </div>

      <div className="overflow-x-auto scroll-thin">
        <table className="w-full min-w-[720px] border-collapse text-left">
          <thead>
            <tr className="border-b border-border">
              {['Candidate', 'Recommendation', 'Asset Assigned', 'Task', 'Priority', 'Window', 'Status'].map(
                (h) => (
                  <th
                    key={h}
                    className="px-3.5 py-2 font-mono text-[9px] font-medium uppercase tracking-[0.1em] text-muted-foreground"
                  >
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {ASSIGNMENTS.map((a) => (
              <tr
                key={a.id}
                className="border-b border-border last:border-b-0 transition-colors hover:bg-muted/40"
              >
                <td className="px-3.5 py-2.5 text-[12px] font-semibold text-foreground">
                  {a.candidate}
                </td>
                <td className="px-3.5 py-2.5">
                  <StatusBadge tone={a.recommendation === 'PRIMARY LEAD' ? 'saffron' : 'navy'}>
                    {a.recommendation}
                  </StatusBadge>
                </td>
                <td className="px-3.5 py-2.5 font-mono text-[12px] text-foreground">{a.asset}</td>
                <td className="px-3.5 py-2.5 text-[12px] text-muted-foreground">{a.task}</td>
                <td className="px-3.5 py-2.5">
                  <StatusBadge tone={priorityTone[a.priority]}>{a.priority}</StatusBadge>
                </td>
                <td className="px-3.5 py-2.5 font-mono text-[12px] tabular-nums text-foreground">
                  {a.window}
                </td>
                <td className="px-3.5 py-2.5">
                  <StatusBadge tone="warn" dot>
                    {a.status}
                  </StatusBadge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
