import { ArrowRight, ChevronRight } from 'lucide-react'
import type { ProcessStage } from '../types/dashboard'

export function ProcessingStatus({ stages }: { stages: ProcessStage[] }) {
  const total = stages.reduce((sum, stage) => sum + stage.count, 0)
  const openQueue = () => document.getElementById('review-queue')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  return <section className="panel processing-panel">
    <div className="panel-heading"><div><h2>Processing status</h2><p>Illustrative distribution by stage</p></div><button className="icon-button" onClick={openQueue} aria-label="Open live review queue"><ChevronRight size={18} /></button></div>
    <div className="stage-total"><strong>{total}</strong><span>synthetic records</span></div>
    <div className="stage-bar" aria-label="Synthetic record distribution">{stages.map(stage => <span key={stage.name} className={stage.color} style={{ width: `${(stage.count / total) * 100}%` }} />)}</div>
    <div className="stage-list">{stages.map(stage => <div key={stage.name} className="stage-row"><span className={`stage-dot ${stage.color}`} /> <span>{stage.name}</span><strong>{stage.count}</strong></div>)}</div>
    <button className="status-link" onClick={openQueue}>Open live review queue <ArrowRight size={15} /></button>
  </section>
}
