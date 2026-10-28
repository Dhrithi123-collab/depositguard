import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { hasReadErrors, lookupRecord, recordListView, resolveAnchorTarget } from '../src/services/workspaceUi.ts'
import type { FDRRecord } from '../src/services/api.ts'

const record: FDRRecord = {
  id: 'synthetic-fdr-001',
  institution_id: 'synthetic-institution-001',
  instrument_reference: 'SYNTHETIC-REF-001',
  workflow_stage: 'draft',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

test('record search never reports a false no-match while records load or fail', () => {
  assert.equal(lookupRecord('REF', record.institution_id, [record], true, '').kind, 'loading')
  assert.equal(lookupRecord('REF', record.institution_id, [record], false, 'API failed').kind, 'error')
  assert.equal(lookupRecord('missing', record.institution_id, [record], false, '').kind, 'not-found')
})

test('record search matches only the loaded records in the selected institution context', () => {
  const result = lookupRecord('synthetic-ref-001', record.institution_id, [record], false, '')
  assert.deepEqual(result, { kind: 'match', record })
  assert.equal(lookupRecord('REF', '', [record], false, '').kind, 'choose-institution')
  assert.equal(lookupRecord('REF', record.institution_id, [], false, '').kind, 'empty')
})

test('record-list failures remain errors and do not expose the first-record empty workflow', () => {
  assert.equal(recordListView([], true, ''), 'loading')
  assert.equal(recordListView([], false, 'API failed'), 'error')
  assert.equal(recordListView([], false, ''), 'empty')
  assert.equal(recordListView([record], false, ''), 'ready')
})

test('navigation falls back to the persistent workspace when a record-only target is absent', () => {
  assert.equal(resolveAnchorTarget('record-evidence', false), 'fdr-workspace')
  assert.equal(resolveAnchorTarget('record-history', false), 'fdr-workspace')
  assert.equal(resolveAnchorTarget('record-evidence', true), 'record-evidence')
})

test('page routes replace the dashboard placeholder date window', () => {
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
  for (const path of ['/dashboard', '/institutions', '/fdr-records', '/documents', '/relationships', '/review-queue', '/audit-trail', '/settings']) assert.ok(app.includes(`'${path}'`))
  assert.doesNotMatch(app, /Illustrative window · 30 days/)
})

test('selected-record read errors expose the shared retry state', () => {
  assert.equal(hasReadErrors([undefined, undefined]), false)
  assert.equal(hasReadErrors([undefined, 'version history failed']), true)
})
