import { useEffect, useState } from 'react'
import { AlertCircle, ClipboardCheck, RefreshCw } from 'lucide-react'
import { ApiError, api, type PriorityQueue } from '../services/api'

type LoadState = { kind: 'unconfigured' } | { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'loaded'; data: PriorityQueue }

export function ReviewQueuePanel({ institutionId, refreshKey }: { institutionId: string; refreshKey: number }) {
  const [state, setState] = useState<LoadState>(institutionId ? { kind: 'loading' } : { kind: 'unconfigured' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!institutionId) {
      setState({ kind: 'unconfigured' })
      return
    }
    const controller = new AbortController()
    setState({ kind: 'loading' })
    api.priorityQueue(institutionId, controller.signal)
      .then((data) => setState({ kind: 'loaded', data }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setState({ kind: 'error', message: error instanceof ApiError ? error.message : 'The live review queue could not be loaded.' })
      })
    return () => controller.abort()
  }, [institutionId, refreshKey, attempt])

  return <section className="panel review-queue-panel" id="review-queue" aria-labelledby="review-queue-title">
    <div className="panel-heading">
      <div><h2 id="review-queue-title">Review queue</h2><p>Advisory order recalculated from current backend records</p></div>
      <span className={`queue-source ${state.kind === 'loaded' ? 'queue-live' : ''}`}>
        {state.kind === 'loaded' ? 'LIVE API DATA' : state.kind === 'error' ? 'API ERROR' : state.kind === 'loading' ? 'CONNECTING' : 'NOT CONNECTED'}
      </span>
    </div>
    {state.kind === 'loading' && <div className="queue-state">Loading the live review queue…</div>}
    {state.kind === 'unconfigured' && <div className="queue-state"><ClipboardCheck size={18} /><div><strong>Select an institution</strong><span>Choose an existing local institution above to load its live queue. No synthetic queue rows are presented as live.</span></div></div>}
    {state.kind === 'error' && <div className="queue-state queue-error"><AlertCircle size={18} /><div><strong>Live queue unavailable</strong><span>{state.message}</span></div><button className="icon-button" onClick={() => setAttempt((value) => value + 1)} aria-label="Retry loading review queue"><RefreshCw size={14} /></button></div>}
    {state.kind === 'loaded' && state.data.items.length === 0 && <div className="queue-empty"><ClipboardCheck size={19} /><strong>No records currently eligible for review.</strong><span>Live API · Policy {state.data.policy_version}</span></div>}
    {state.kind === 'loaded' && state.data.items.length > 0 && <div className="queue-items">
      {state.data.items.map((item) => <article className="queue-item" key={item.record_id}>
        <div className="queue-score"><strong>{item.score}<small>/100</small></strong><span>{item.priority_category_label}</span></div>
        <div className="queue-record"><strong>{item.record_id}</strong><span>Workflow: {item.workflow_stage.replace(/_/g, ' ')}</span>
          <div className="queue-factor-list">{item.factors.map((factor) => <p key={factor.factor}><b>{factor.factor.replace(/_/g, ' ')} · +{factor.points}</b> — {factor.explanation}</p>)}</div>
          {item.missing_inputs.map((missing) => <small className="queue-missing" key={missing}>{missing}</small>)}
          <small>{item.relevant_deadline ? `Deadline: ${new Date(item.relevant_deadline).toLocaleDateString()}` : 'No deadline is stored for this record.'}</small>
          <small>Policy {item.policy_version} · calculated {new Date(item.calculated_at).toLocaleString()}</small>
        </div>
      </article>)}
      <div className="queue-footnote">Priority is advisory and is not a fraud or authenticity assessment. Source: live institution-scoped API.</div>
    </div>}
  </section>
}
