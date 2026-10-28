import { useEffect, useState } from 'react'
import { Activity, AlertCircle, Files, RefreshCw, ShieldCheck } from 'lucide-react'
import { ApiError, api, type DashboardSummary, type PriorityQueue, type WorkflowConfig } from '../services/api'
import { Link } from 'react-router-dom'

const errorText = (error: unknown) => error instanceof ApiError ? error.message : error instanceof Error ? error.message : 'The API request could not be completed.'
const dateText = (value: string) => new Date(value).toLocaleString()

export function DashboardOverview({ institutionId, refreshKey, workflow }: { institutionId: string; refreshKey: number; workflow?: WorkflowConfig }) {
  const [summary, setSummary] = useState<DashboardSummary>()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [queue, setQueue] = useState<PriorityQueue>()
  const [queueError, setQueueError] = useState('')
  const [queueLoading, setQueueLoading] = useState(false)
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    if (!institutionId) { setSummary(undefined); setQueue(undefined); setError(''); setQueueError(''); return }
    let active = true
    setLoading(true); setError(''); setSummary(undefined)
    api.dashboardSummary(institutionId).then((value) => { if (active) setSummary(value) })
      .catch((reason: unknown) => { if (active) setError(errorText(reason)) })
      .finally(() => { if (active) setLoading(false) })
    setQueueLoading(true); setQueueError(''); setQueue(undefined)
    api.priorityQueue(institutionId).then((value) => { if (active) setQueue(value) })
      .catch((reason: unknown) => { if (active) setQueueError(errorText(reason)) })
      .finally(() => { if (active) setQueueLoading(false) })
    return () => { active = false }
  }, [institutionId, refreshKey, retry])

  const stageLabel = (key: string) => workflow?.stages.find((stage) => stage.key === key)?.label ?? key.replace(/_/g, ' ')
  const stageRows = Object.entries(summary?.stage_counts ?? {})
  const checkRows = Object.entries(summary?.integrity_check_counts ?? {})
  const totalChecks = checkRows.reduce((sum, [, count]) => sum + count, 0)
  return <>
    <div className="section-label"><span>LOCAL OVERVIEW</span><span className="label-line" /><span className="queue-source queue-live">LOCAL API DATA</span></div>
    {!institutionId && <section className="panel dashboard-state" role="status"><strong>Select an institution to view its local data.</strong><span>Choose an institution in the FDR workspace below. No cross-institution totals are shown.</span></section>}
    {institutionId && loading && <section className="panel dashboard-state" role="status">Loading local overview for the selected institution…</section>}
    {institutionId && error && <section className="panel dashboard-state workspace-inline-error" role="alert"><AlertCircle size={16} /> Overview unavailable: {error}<button className="text-button" onClick={() => setRetry((value) => value + 1)}><RefreshCw size={14} /> Retry</button></section>}
    {institutionId && summary && !loading && <>
      <section className="metrics-grid" aria-label="Selected institution local data">
        <article className="metric-card"><div className="metric-top"><span>FDR records</span><Files size={17} /></div><div className="metric-value">{summary.total_records}</div><div className="metric-bottom"><span>In selected institution</span></div></article>
        <article className="metric-card"><div className="metric-top"><span>Eligible for priority review</span><Activity size={17} /></div><div className="metric-value">{queueLoading ? '…' : queueError ? '—' : queue?.items.length ?? 0}</div><div className="metric-bottom"><span>{queueError ? 'Priority queue unavailable' : 'Based on configured local policy'}</span>{queueError && <button className="text-button" onClick={() => setRetry((value) => value + 1)}>Retry</button>}</div></article>
        <article className="metric-card"><div className="metric-top"><span>Documents</span><Files size={17} /></div><div className="metric-value">{summary.document_count}</div><div className="metric-bottom"><span>Stored document records</span></div></article>
        <article className="metric-card"><div className="metric-top"><span>Integrity checks</span><ShieldCheck size={17} /></div><div className="metric-value">{totalChecks}</div><div className="metric-bottom"><span>Recorded local checks</span></div></article>
      </section>
      <div className="content-grid">
        <section className="panel activity-panel"><div className="panel-heading"><div><h2>Recent persisted activity</h2><p>Newest recorded audit events for this institution</p></div><Link className="text-button" to="/audit-trail">Open audit trail →</Link></div>
          {!summary.recent_activity.length && <p className="detail-empty">No audit activity is recorded for this institution.</p>}
          <div className="activity-list">{summary.recent_activity.map((item) => <article className="audit-row" key={item.id}><span className="audit-dot" /><div><strong>{item.event_type.replace(/_/g, ' ')}</strong><span>{item.from_stage && item.to_stage ? `${stageLabel(item.from_stage)} → ${stageLabel(item.to_stage)}` : item.reason || 'Recorded event'}</span><small>{dateText(item.created_at)} · actor reference {item.actor_id} (historical IDs may be unverified) · {item.fdr_record_id ? `FDR ${item.fdr_record_id}` : 'Institution event'}</small></div></article>)}</div>
        </section>
        <section className="panel processing-panel"><div className="panel-heading"><div><h2>Workflow stage counts</h2><p>Current persisted records by workflow stage</p></div></div>
          {!stageRows.length && <p className="detail-empty">No FDR records are recorded for this institution.</p>}
          <div className="stage-total"><strong>{summary.total_records}</strong><span>local records</span></div>
          <div className="stage-list">{stageRows.map(([key, count]) => <div className="stage-row" key={key}><span>{stageLabel(key)}</span><strong>{count}</strong></div>)}</div>
          <h3 className="overview-subheading">Integrity outcomes</h3>
          {!checkRows.length && <p className="detail-empty">No integrity checks are recorded.</p>}
          <div className="stage-list">{checkRows.map(([result, count]) => <div className="stage-row" key={result}><span>{result}</span><strong>{count}</strong></div>)}</div>
          <p className="detail-security-note">PASS means stored bytes matched the recorded upload-time digest. It does not prove bank authenticity.</p>
        </section>
      </div>
    </>}
  </>
}
