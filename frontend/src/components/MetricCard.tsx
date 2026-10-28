import { ArrowUpRight, AlertTriangle, CheckCircle2, Clock3, Files } from 'lucide-react'
import type { Metric } from '../types/dashboard'

const icons = { blue: Files, green: CheckCircle2, amber: Clock3, rose: AlertTriangle }

export function MetricCard({ metric }: { metric: Metric }) {
  const Icon = icons[metric.tone]
  return <article className="metric-card">
    <div className="metric-top"><span>{metric.label}</span><span className={`metric-icon ${metric.tone}`}><Icon size={17} /></span></div>
    <div className="metric-value">{metric.value}</div>
    <div className="metric-bottom"><span>{metric.detail}</span><span className={`metric-trend ${metric.tone}`}>{metric.trend} <ArrowUpRight size={13} /></span></div>
  </article>
}
