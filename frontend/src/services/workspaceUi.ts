import type { FDRRecord } from './api'

export type RecordLookup =
  | { kind: 'empty-query' }
  | { kind: 'choose-institution' }
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'empty' }
  | { kind: 'not-found' }
  | { kind: 'match'; record: FDRRecord }

export type RecordListView = 'loading' | 'error' | 'empty' | 'ready'

export function recordListView(records: FDRRecord[], loading: boolean, error: string): RecordListView {
  if (loading) return 'loading'
  if (error) return 'error'
  return records.length ? 'ready' : 'empty'
}

export function lookupRecord(
  query: string,
  institutionId: string,
  records: FDRRecord[],
  loading: boolean,
  error: string,
): RecordLookup {
  const normalizedQuery = query.trim().toLocaleLowerCase()
  if (!normalizedQuery) return { kind: 'empty-query' }
  if (!institutionId) return { kind: 'choose-institution' }
  if (error) return { kind: 'error' }
  if (loading) return { kind: 'loading' }
  if (!records.length) return { kind: 'empty' }
  const record = records.find((item) =>
    item.id.toLocaleLowerCase().includes(normalizedQuery)
    || (item.instrument_reference ?? '').toLocaleLowerCase().includes(normalizedQuery),
  )
  return record ? { kind: 'match', record } : { kind: 'not-found' }
}

export function resolveAnchorTarget(
  requestedTarget: string,
  targetExists: boolean,
  fallbackTarget = 'fdr-workspace',
): string {
  return targetExists ? requestedTarget : fallbackTarget
}

export function hasReadErrors(errors: Array<string | undefined>): boolean {
  return errors.some(Boolean)
}
