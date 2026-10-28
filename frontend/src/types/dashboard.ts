export type Metric = {
  label: string
  value: string
  detail: string
  trend?: string
  tone: 'blue' | 'green' | 'amber' | 'rose'
}

export type Activity = {
  title: string
  subject: string
  time: string
  initials: string
  tone: string
}

export type ProcessStage = {
  name: string
  count: number
  color: string
}
