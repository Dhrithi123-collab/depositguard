import type { Activity, Metric, ProcessStage } from '../types/dashboard'

// Presentation-only synthetic values. These are not operational or AICTE records.
export const demoMetrics: Metric[] = [
  { label: 'Pending reviews', value: '18', detail: 'Across 6 synthetic institutions', trend: '4 need attention', tone: 'blue' },
  { label: 'Completed checks', value: '42', detail: 'Illustrative demo activity', trend: 'This month', tone: 'green' },
  { label: 'Upcoming deadlines', value: '7', detail: 'Within the demo window', trend: 'Next 30 days', tone: 'amber' },
  { label: 'Flagged records', value: '3', detail: 'Demo review signals only', trend: 'Review required', tone: 'rose' },
]

export const demoActivity: Activity[] = [
  { title: 'Document set received', subject: 'Synthetic record · DG-DEMO-1042', time: '12 min ago', initials: 'AR', tone: 'violet' },
  { title: 'Review marked complete', subject: 'Synthetic record · DG-DEMO-1038', time: '48 min ago', initials: 'SM', tone: 'blue' },
  { title: 'Date difference flagged', subject: 'Synthetic record · DG-DEMO-1031', time: '2 hours ago', initials: 'RK', tone: 'amber' },
  { title: 'Demo record added', subject: 'Synthetic record · DG-DEMO-1029', time: 'Yesterday', initials: 'NP', tone: 'green' },
]

export const demoStages: ProcessStage[] = [
  { name: 'Submitted', count: 12, color: 'bg-blue-500' },
  { name: 'In review', count: 18, color: 'bg-indigo-500' },
  { name: 'Awaiting information', count: 7, color: 'bg-amber-400' },
  { name: 'Completed', count: 42, color: 'bg-emerald-500' },
]
