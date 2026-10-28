import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, ArrowRightLeft, FileText, GitBranch, Link2, RefreshCw, ScanSearch, ShieldAlert } from 'lucide-react'
import { ApiError, api, type GraphResult } from '../services/api'

type Props = { institutionId: string; recordId: string; refreshKey: number }
type NodeType = 'FDR record' | 'Document' | 'Document version' | 'Evidence event' | 'Lifecycle event'
type DemoNode = { id: string; type: NodeType; title: string; detail: string }
type DemoEdge = { source: string; target: string; type: string; status: string }

const demoNodes: DemoNode[] = [
  { id: 'DG-DEMO-1042', type: 'FDR record', title: 'Synthetic FDR · DG-DEMO-1042', detail: 'Illustrative record node' },
  { id: 'DG-DEMO-1047', type: 'FDR record', title: 'Synthetic FDR · DG-DEMO-1047', detail: 'Illustrative renewal record' },
  { id: 'DOC-DEMO-01', type: 'Document', title: 'Supporting evidence', detail: 'Synthetic document association' },
  { id: 'VER-DEMO-01', type: 'Document version', title: 'Version 1', detail: 'Immutable version node' },
  { id: 'CHK-DEMO-01', type: 'Evidence event', title: 'SHA-256 integrity check', detail: 'Illustrative event · not executed' },
]
const demoEdges: DemoEdge[] = [
  { source: 'DG-DEMO-1047', target: 'DG-DEMO-1042', type: 'renewal_of', status: 'Requires human review' },
  { source: 'DG-DEMO-1042', target: 'DOC-DEMO-01', type: 'has_document', status: 'Schema-linked association' },
  { source: 'DOC-DEMO-01', target: 'VER-DEMO-01', type: 'has_version', status: 'Schema-linked association' },
  { source: 'VER-DEMO-01', target: 'CHK-DEMO-01', type: 'has_integrity_check', status: 'Not run' },
]
const iconFor: Record<NodeType, typeof GitBranch> = {
  'FDR record': GitBranch, Document: FileText, 'Document version': FileText,
  'Evidence event': ScanSearch, 'Lifecycle event': ArrowRightLeft,
}

function DemoPreview() {
  const [selectedId, setSelectedId] = useState(demoNodes[0].id)
  const selected = demoNodes.find((node) => node.id === selectedId) ?? demoNodes[0]
  const connected = useMemo(() => demoEdges.filter((edge) => edge.source === selectedId || edge.target === selectedId), [selectedId])
  return <div className="graph-layout">
    <div className="graph-node-list" aria-label="Synthetic graph nodes">{demoNodes.map((node) => {
      const Icon = iconFor[node.type]
      return <button className={`graph-node ${node.id === selectedId ? 'selected' : ''}`} key={node.id} onClick={() => setSelectedId(node.id)} aria-pressed={node.id === selectedId}>
        <span className="graph-node-icon"><Icon size={15} /></span><span className="graph-node-copy"><strong>{node.title}</strong><small>{node.type} · {node.detail}</small></span>
      </button>
    })}</div>
    <div className="graph-detail" aria-live="polite">
      <div className="graph-detail-title"><Link2 size={16} /><div><strong>{selected.title}</strong><span>{connected.length} adjacent illustrative links</span></div></div>
      <ul className="graph-edge-list">{connected.map((edge) => {
        const otherId = edge.source === selectedId ? edge.target : edge.source
        const other = demoNodes.find((node) => node.id === otherId)
        return <li key={`${edge.source}-${edge.target}`}><span className="graph-edge-type">{edge.type}</span><span className="graph-edge-target">{other?.title ?? otherId}<small>{edge.status}</small></span></li>
      })}</ul>
      <p className="graph-sample-note">Synthetic preview only. Not fetched from the backend; no verification result is shown.</p>
    </div>
  </div>
}

export function RelationshipExplorer({ institutionId, recordId, refreshKey }: Props) {
  const [algorithm, setAlgorithm] = useState<'BFS' | 'DFS'>('BFS')
  const [state, setState] = useState<{ kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'loaded'; data: GraphResult } | { kind: 'idle' }>(
    institutionId && recordId ? { kind: 'loading' } : { kind: 'idle' },
  )
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const [retryAttempt, setRetryAttempt] = useState(0)

  useEffect(() => {
    if (!institutionId || !recordId) {
      setState({ kind: 'idle' })
      return
    }
    let active = true
    setState({ kind: 'loading' })
    api.graph(institutionId, recordId, algorithm).then((data) => {
      if (!active) return
      setSelectedNodeId(data.start_node.entity_id)
      setState({ kind: 'loaded', data })
    }).catch((error: unknown) => {
      if (!active) return
      setState({ kind: 'error', message: error instanceof ApiError ? error.message : 'The relationship graph could not be loaded.' })
    })
    return () => { active = false }
  }, [institutionId, recordId, algorithm, refreshKey, retryAttempt])

  const graph = state.kind === 'loaded' ? state.data : undefined
  const selected = graph?.nodes.find((node) => node.entity_id === selectedNodeId)
  const connectedEdges = graph?.edges.filter((edge) =>
    (edge.source_id === selectedNodeId || edge.target_id === selectedNodeId)
  ) ?? []
  const labels = new Map(graph?.nodes.map((node) => [node.entity_id, node.label]) ?? [])

  return <section className="panel graph-panel" aria-labelledby="graph-title">
    <div className="panel-heading graph-heading">
      <div><h2 id="graph-title">Relationship explorer</h2><p>Recorded links across FDR records, documents, versions, and events</p></div>
      {graph ? <label className="graph-algorithm">Traversal <select value={algorithm} onChange={(event) => setAlgorithm(event.target.value as 'BFS' | 'DFS')}><option value="BFS">BFS</option><option value="DFS">DFS</option></select></label> : <span className="demo-pill">{state.kind === 'error' ? 'API ERROR' : state.kind === 'loading' ? 'CONNECTING' : institutionId ? 'SELECT RECORD' : 'SYNTHETIC SAMPLE'}</span>}
    </div>
    <div className="graph-caveat"><ShieldAlert size={15} /><span>Links are recorded associations, not proof of authenticity, validity, or fraud.</span></div>
    {state.kind === 'loading' && <div className="queue-state">Loading connected graph from the API…</div>}
    {state.kind === 'error' && <div className="queue-state queue-error"><AlertCircle size={17} /><div><strong>Live graph unavailable</strong><span>{state.message}</span></div><button className="icon-button" onClick={() => setRetryAttempt((value) => value + 1)} aria-label="Retry loading relationship graph"><RefreshCw size={14} /></button></div>}
    {state.kind === 'idle' && institutionId && <div className="queue-empty"><GitBranch size={18} /><strong>Select or create an FDR record to explore its live graph.</strong></div>}
    {state.kind === 'idle' && !institutionId && <><span className="demo-pill graph-synthetic-badge">SYNTHETIC PREVIEW</span><DemoPreview /></>}
    {graph && <>
      <div className="graph-meta">{graph.algorithm} · start depth 0 · maximum depth {graph.max_depth} · {graph.nodes.length} nodes{graph.truncated ? ' · truncated at configured node cap' : ''}</div>
      <div className="graph-layout">
        <div className="graph-node-list" aria-label="Live graph nodes">{graph.nodes.map((node) => <button className={`graph-node ${node.entity_id === selectedNodeId ? 'selected' : ''}`} key={`${node.entity_type}-${node.entity_id}`} onClick={() => setSelectedNodeId(node.entity_id)} aria-pressed={node.entity_id === selectedNodeId}>
          <span className="graph-node-icon"><GitBranch size={15} /></span><span className="graph-node-copy"><strong>{node.label}</strong><small>{node.entity_type.replace(/_/g, ' ')} · depth {node.depth} · {node.entity_id}</small></span>
        </button>)}</div>
        <div className="graph-detail" aria-live="polite">
          <div className="graph-detail-title"><Link2 size={16} /><div><strong>{selected?.label ?? 'Selected node'}</strong><span>{connectedEdges.length} traversal edge(s)</span></div></div>
          {connectedEdges.length ? <ul className="graph-edge-list">{connectedEdges.map((edge) => <li key={edge.edge_id}>
            <span className="graph-edge-type">{edge.relationship_label}<small>{edge.relationship_type}</small></span>
            <span className="graph-edge-target"><b>{labels.get(edge.source_id) ?? edge.source_id}</b> → <b>{labels.get(edge.target_id) ?? edge.target_id}</b><small>depth {edge.traversal_depth}{edge.review_status ? ` · ${edge.review_status.replace(/_/g, ' ')}` : ''}</small></span>
          </li>)}</ul> : <p className="graph-empty">No discovery edges for this node in the current traversal.</p>}
          <p className="graph-sample-note">Live response from the institution-scoped API. Edge arrows show the stored source → target direction.</p>
        </div>
      </div>
    </>}
  </section>
}
