import { ArrowRight, Check, FilePlus2, Flag, Upload } from 'lucide-react'
import type { Activity } from '../types/dashboard'

const icons = [Upload, Check, Flag, FilePlus2]

export function ActivityList({ activities }: { activities: Activity[] }) {
  const openWorkspace = () => (document.getElementById('record-history') ?? document.getElementById('fdr-workspace'))?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  return <section className="panel activity-panel">
    <div className="panel-heading"><div><h2>Recent activity</h2><p>Latest updates across the demo workspace</p></div><button className="text-button" onClick={openWorkspace}>Open live record history <ArrowRight size={15} /></button></div>
    <div className="activity-list">{activities.map((item, index) => {
      const Icon = icons[index % icons.length]
      return <div className="activity-row" key={item.subject}>
        <div className={`activity-icon ${item.tone}`}><Icon size={16} /></div>
        <div className="activity-copy"><strong>{item.title}</strong><span>{item.subject}</span></div>
        <time>{item.time}</time>
        <div className="avatar">{item.initials}</div>
      </div>
    })}</div>
    <div className="synthetic-caption"><span className="demo-dot" />All activity shown is illustrative synthetic demo data</div>
  </section>
}
