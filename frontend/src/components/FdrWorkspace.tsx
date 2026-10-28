import { useEffect, useRef, useState } from 'react'
import { AlertCircle, FileCheck2, FileUp, Plus, RefreshCw, SearchCheck, Workflow } from 'lucide-react'
import { ApiError, api, CONFIGURED_INSTITUTION_ID, type AuditEvent, type EvidenceCheck, type FDRDocument, type FDRRecord, type GraphPolicy, type Institution, type PriorityPolicyInfo, type UploadPolicyInfo, type UrgencyScore, type WorkflowConfig } from '../services/api'
import { hasReadErrors, lookupRecord, recordListView } from '../services/workspaceUi'
import { RelationshipExplorer } from './RelationshipExplorer'
import { ReviewQueuePanel } from './ReviewQueuePanel'
import { DashboardOverview } from './DashboardOverview'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './Auth'
import { UserAdministration } from './UserAdministration'

type DetailState = {
  loading: boolean
  record?: FDRRecord
  recordError?: string
  audit: AuditEvent[]
  auditError?: string
  documents: FDRDocument[]
  documentError?: string
  evidence: EvidenceCheck[]
  evidenceError?: string
  relationships: Awaited<ReturnType<typeof api.listRelationships>>
  relationshipError?: string
  score?: UrgencyScore
  scoreError?: string
}

const emptyDetail: DetailState = { loading: false, audit: [], documents: [], evidence: [], relationships: [] }
const errorText = (error: unknown) => error instanceof ApiError ? error.message : error instanceof Error ? error.message : 'The API request could not be completed.'
const dateText = (value: string) => new Date(value).toLocaleString()

export function FdrWorkspace({ onInstitutionChange, onDataChange, overviewRefresh }: { onInstitutionChange: (id: string) => void; onDataChange: () => void; overviewRefresh: number }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { session } = useAuth()
  const user = session!.user
  const actorId = user.id
  const page = pathname.slice(1)
  const [institutions, setInstitutions] = useState<Institution[]>([])
  const [institutionId, setInstitutionId] = useState('')
  const [institutionLoading, setInstitutionLoading] = useState(true)
  const [institutionRetry, setInstitutionRetry] = useState(0)
  const [institutionError, setInstitutionError] = useState('')
  const [configuredInstitutionMessage, setConfiguredInstitutionMessage] = useState('')
  const [institutionName, setInstitutionName] = useState('')
  const [records, setRecords] = useState<FDRRecord[]>([])
  const [recordsLoading, setRecordsLoading] = useState(false)
  const [recordsRetry, setRecordsRetry] = useState(0)
  const [recordsError, setRecordsError] = useState('')
  const [searchMessage, setSearchMessage] = useState('')
  const [recordId, setRecordId] = useState('')
  const [refreshToken, setRefreshToken] = useState(0)
  const [detail, setDetail] = useState<DetailState>(emptyDetail)
  const [workflow, setWorkflow] = useState<WorkflowConfig>()
  const [workflowError, setWorkflowError] = useState('')
  const [graphPolicy, setGraphPolicy] = useState<GraphPolicy['policy']>()
  const [graphPolicyError, setGraphPolicyError] = useState('')
  const [priorityPolicy, setPriorityPolicy] = useState<PriorityPolicyInfo>()
  const [priorityPolicyError, setPriorityPolicyError] = useState('')
  const [uploadPolicy, setUploadPolicy] = useState<UploadPolicyInfo>()
  const [uploadPolicyError, setUploadPolicyError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)
  const [actionError, setActionError] = useState('')
  const [actionNotice, setActionNotice] = useState('')
  const [instrumentReference, setInstrumentReference] = useState('')
  const [targetStage, setTargetStage] = useState('')
  const [transitionReason, setTransitionReason] = useState('')
  const [categoryKey, setCategoryKey] = useState('')
  const [versionDocumentId, setVersionDocumentId] = useState('')
  const [uploadFile, setUploadFile] = useState<File>()
  const [fileInputKey, setFileInputKey] = useState(0)
  const [relationshipTarget, setRelationshipTarget] = useState('')
  const [relationshipType, setRelationshipType] = useState('')
  const [relationshipNote, setRelationshipNote] = useState('')

  useEffect(() => {
    let active = true
    setInstitutionLoading(true)
    setInstitutionError('')
    setWorkflowError('')
    setGraphPolicyError('')
    api.listInstitutions().then((items) => {
      if (!active) return
      setInstitutions(items)
      if (CONFIGURED_INSTITUTION_ID) {
        if (items.some((item) => item.id === CONFIGURED_INSTITUTION_ID)) { setInstitutionId(CONFIGURED_INSTITUTION_ID); setRecordsLoading(true); onInstitutionChange(CONFIGURED_INSTITUTION_ID) }
        else setConfiguredInstitutionMessage('The configured institution ID was not found in the local API. Choose an institution or create one below.')
      } else if (items.length === 1) {
        setInstitutionId(items[0].id); setRecordsLoading(true); onInstitutionChange(items[0].id)
      }
      setInstitutionError('')
    }).catch((error: unknown) => {
      if (active) setInstitutionError(errorText(error))
    }).finally(() => { if (active) setInstitutionLoading(false) })
    api.getWorkflow().then((result) => { if (active) { setWorkflow(result.config); setWorkflowError('') } }).catch((error: unknown) => { if (active) setWorkflowError(errorText(error)) })
    api.getGraphPolicy().then((result) => { if (active) { setGraphPolicy(result.policy); setGraphPolicyError('') } }).catch((error: unknown) => { if (active) setGraphPolicyError(errorText(error)) })
    return () => { active = false }
  }, [institutionRetry, onInstitutionChange])

  useEffect(() => {
    if (page !== 'settings') return
    let active = true
    setPriorityPolicyError(''); setUploadPolicyError('')
    api.priorityPolicy().then((value) => { if (active) setPriorityPolicy(value) }).catch((error: unknown) => { if (active) setPriorityPolicyError(errorText(error)) })
    api.uploadPolicy().then((value) => { if (active) setUploadPolicy(value) }).catch((error: unknown) => { if (active) setUploadPolicyError(errorText(error)) })
    return () => { active = false }
  }, [page])

  useEffect(() => {
    if (!institutionId) {
      setRecords([])
      setRecordId('')
      setRecordsLoading(false)
      setRecordsError('')
      return
    }
    let active = true
    setRecordsLoading(true)
    setRecordsError('')
    api.listRecords(institutionId).then((items) => {
      if (!active) return
      setRecords(items)
      setRecordId((current) => items.some((item) => item.id === current) ? current : '')
      setRecordsError('')
    }).catch((error: unknown) => { if (active) setRecordsError(errorText(error)) })
      .finally(() => { if (active) setRecordsLoading(false) })
    return () => { active = false }
  }, [institutionId, refreshToken, recordsRetry])

  useEffect(() => {
    const handleSearch = (event: Event) => {
      const rawQuery = (event as CustomEvent<string>).detail
      const result = lookupRecord(rawQuery, institutionId, records, recordsLoading, recordsError)
      if (result.kind === 'empty-query') setSearchMessage('Enter an FDR ID or instrument reference to search.')
      else if (result.kind === 'choose-institution') {
        setSearchMessage('Choose an institution first. Search is scoped to the selected institution.')
        navigate('/institutions')
      } else if (result.kind === 'loading') setSearchMessage('FDR records are still loading. Wait for the list to finish, then search again.')
      else if (result.kind === 'error') {
        setSearchMessage('Search is unavailable because the selected institution’s record list failed to load. Retry the record list below.')
        navigate('/fdr-records')
      } else if (result.kind === 'empty') setSearchMessage('No FDR records are available in the selected institution yet.')
      else if (result.kind === 'not-found') setSearchMessage(`No FDR ID or instrument reference matched “${rawQuery.trim()}” in the selected institution.`)
      else {
        setRecordId(result.record.id)
        setSearchMessage(`Selected ${result.record.id} in the current institution.`)
        navigate('/fdr-records')
      }
    }
    window.addEventListener('depositguard:search-record', handleSearch)
    return () => window.removeEventListener('depositguard:search-record', handleSearch)
  }, [institutionId, records, recordsLoading, recordsError, navigate])

  useEffect(() => {
    if (!workflow?.document_requirements.length) return
    setCategoryKey((current) => workflow.document_requirements.some((item) => item.key === current) ? current : workflow.document_requirements[0].key)
  }, [workflow])

  useEffect(() => {
    setTargetStage('')
    setUploadFile(undefined)
    setFileInputKey((value) => value + 1)
    setVersionDocumentId('')
    setRelationshipTarget('')
    setRelationshipType('')
  }, [institutionId, recordId])

  useEffect(() => {
    if (!institutionId || !recordId) {
      setDetail(emptyDetail)
      return
    }
    let active = true
    setDetail({ ...emptyDetail, loading: true })
    const read = async <T,>(request?: Promise<T>) => {
      if (!request) return undefined
      try { return { data: await request } as const }
      catch (error) { return { error } as const }
    }
    const requests = Promise.all([
      read(page === 'fdr-records' ? api.getRecord(institutionId, recordId) : undefined),
      read(page === 'audit-trail' ? api.getAudit(institutionId, recordId) : undefined),
      read(page === 'documents' ? api.listDocuments(institutionId, recordId) : undefined),
      read(page === 'documents' ? api.listEvidence(institutionId, recordId) : undefined),
      read(page === 'relationships' ? api.listRelationships(institutionId, recordId) : undefined),
      read(page === 'review-queue' ? api.urgencyScore(institutionId, recordId) : undefined),
    ])
    requests.then(async ([recordResult, auditResult, documentResult, evidenceResult, relationshipResult, scoreResult]) => {
      const docs = (documentResult && 'data' in documentResult ? documentResult.data : undefined) ?? []
      const versions = await Promise.all(docs.map(async (document) => {
        try { return { items: await api.listVersions(institutionId, recordId, document.id), error: undefined } }
        catch (error) { return { items: document.latest_version ? [document.latest_version] : [], error: errorText(error) } }
      }))
      if (!active) return
      setDetail({
        loading: false,
        record: recordResult && 'data' in recordResult ? recordResult.data : undefined,
        recordError: recordResult && 'error' in recordResult ? errorText(recordResult.error) : undefined,
        audit: (auditResult && 'data' in auditResult ? auditResult.data : undefined) ?? [],
        auditError: auditResult && 'error' in auditResult ? errorText(auditResult.error) : undefined,
        documents: docs.map((document, index) => ({ ...document, versions: versions[index].items, versions_error: versions[index].error })),
        documentError: documentResult && 'error' in documentResult ? errorText(documentResult.error) : undefined,
        evidence: (evidenceResult && 'data' in evidenceResult ? evidenceResult.data : undefined) ?? [],
        evidenceError: evidenceResult && 'error' in evidenceResult ? errorText(evidenceResult.error) : undefined,
        relationships: (relationshipResult && 'data' in relationshipResult ? relationshipResult.data : undefined) ?? [],
        relationshipError: relationshipResult && 'error' in relationshipResult ? errorText(relationshipResult.error) : undefined,
        score: scoreResult && 'data' in scoreResult ? scoreResult.data : undefined,
        scoreError: scoreResult && 'error' in scoreResult ? errorText(scoreResult.error) : undefined,
      })
    })
    return () => { active = false }
  }, [institutionId, recordId, refreshToken, page])

  const runAction = async (successMessage: string | ((result: unknown) => string), action: () => Promise<unknown>) => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    setActionError('')
    setActionNotice('')
    try {
      const result = await action()
      setActionNotice(typeof successMessage === 'function' ? successMessage(result) : successMessage)
      setRefreshToken((value) => value + 1)
      onDataChange()
    } catch (error) {
      setActionError(errorText(error))
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  const createInstitution = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void runAction('Institution created in the local backend.', async () => {
      const created = await api.createInstitution(institutionName.trim(), actorId.trim())
      setInstitutionId(created.id)
      setRecordsLoading(true)
      setRecordsError('')
      onInstitutionChange(created.id)
      setInstitutionName('')
      try {
        setInstitutions(await api.listInstitutions())
        setInstitutionError('')
      } catch (error) {
        setInstitutions((current) => [created, ...current.filter((item) => item.id !== created.id)])
        setInstitutionError(`Created successfully, but the institution list could not refresh: ${errorText(error)}`)
      }
    })
  }
  const createRecord = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!institutionId) return
    void runAction('FDR record created.', async () => {
      const created = await api.createRecord(institutionId, instrumentReference.trim() || null, actorId.trim())
      setRecords((current) => [created, ...current.filter((item) => item.id !== created.id)])
      setRecordId(created.id)
      setInstrumentReference('')
    })
  }
  const transitionRecord = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!institutionId || !recordId || !targetStage) return
    void runAction('Workflow stage updated and audit history refreshed.', async () => {
      const updated = await api.transition(institutionId, recordId, targetStage, actorId.trim(), transitionReason.trim())
      setRecords((current) => current.map((item) => item.id === updated.id ? updated : item))
      setTransitionReason('')
    })
  }
  const upload = () => {
    if (!institutionId || !recordId || !categoryKey || !uploadFile) return
    void runAction((result) => {
      const document = result as FDRDocument
      const version = document.latest_version
      return version
        ? `Uploaded ${version.original_filename} as version ${version.version_number} of document ${document.id}. Document list, versions, evidence, and priority are refreshing.`
        : `Uploaded document ${document.id}. Document list and evidence are refreshing.`
    }, async () => {
      const document = await api.uploadDocument(institutionId, recordId, categoryKey, actorId.trim(), uploadFile, versionDocumentId || undefined)
      setUploadFile(undefined)
      setFileInputKey((value) => value + 1)
      setVersionDocumentId('')
      return document
    })
  }
  const runIntegrityCheck = (documentId: string, versionId: string) => {
    if (!institutionId || !recordId) return
    void runAction((result) => {
      const check = result as EvidenceCheck
      return `${check.result_status} for version ${versionId}: ${check.explanation}`
    }, async () => {
      const check = await api.integrityCheck(institutionId, recordId, documentId, versionId, actorId.trim())
      setDetail((current) => ({
        ...current,
        evidence: [check, ...current.evidence.filter((item) => item.id !== check.id)],
        evidenceError: undefined,
      }))
      return check
    })
  }
  const createRelationship = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!institutionId || !recordId || !relationshipTarget || !relationshipType) return
    void runAction('Relationship recorded. The graph was refreshed.', () => api.createRelationship(institutionId, recordId, relationshipTarget, relationshipType, actorId.trim(), relationshipNote.trim()))
  }

  const hasDetailReadError = hasReadErrors([
    detail.recordError, detail.auditError, detail.documentError, detail.evidenceError,
    detail.relationshipError, detail.scoreError,
    ...detail.documents.map((item) => item.versions_error),
  ])
  const hasConfigurationReadError = hasReadErrors([workflowError, graphPolicyError])
  const recordsView = recordListView(records, recordsLoading, recordsError)
  const role = user.system_admin ? 'system_admin' : user.memberships.find((membership) => membership.institution_id === institutionId)?.role
  const availableTransitions = workflow?.transitions.filter((item) => {
    if (item.from_stage !== detail.record?.workflow_stage) return false
    if (role === 'system_admin') return true
    if (role === 'approver') return workflow?.decision_stages?.includes(item.to_stage) ?? false
    if (role === 'reviewer') return workflow?.clarification_stages?.includes(item.to_stage) ?? false
    return role === 'institution_admin' && !(workflow?.decision_stages?.includes(item.to_stage) ?? false)
  }) ?? []
  const canCreateInstitution = user.system_admin
  const canManageRecords = role === 'system_admin' || role === 'institution_admin'
  const canTransition = canManageRecords || role === 'approver' || role === 'reviewer'
  const canUpload = canManageRecords || role === 'document_officer'
  const canCheckIntegrity = canUpload || role === 'reviewer' || role === 'approver'
  const canManageRelationships = canManageRecords || role === 'reviewer'

  return <>
    {page === 'dashboard' && <DashboardOverview institutionId={institutionId} refreshKey={overviewRefresh} workflow={workflow} />}
    {page === 'settings' && <section className="panel settings-panel"><div className="panel-heading"><div><h2>System status and configuration</h2><p>Local demonstration environment · policy settings are read-only</p></div><span className="queue-source queue-live">AUTHENTICATED LOCAL APP</span></div><p>This build uses the local DepositGuard database. It is not connected to AICTE or bank systems and does not perform live bank verification. Use synthetic data only.</p><div className="settings-list"><div><strong>Workflow policy</strong><span>{workflow ? `${workflow.version} · ${workflow.stages.length} stages · ${workflow.transitions.length} transitions` : workflowError ? `Unavailable: ${workflowError}` : 'Loading configuration…'}</span></div><div><strong>Relationship policy</strong><span>{graphPolicy ? `${graphPolicy.version} · ${graphPolicy.relationship_types.length} relationship types · max depth ${graphPolicy.max_traversal_depth} · max nodes ${graphPolicy.max_nodes}` : graphPolicyError ? `Unavailable: ${graphPolicyError}` : 'Loading configuration…'}</span></div><div><strong>Document categories</strong><span>{workflow?.document_requirements.map((item) => item.label).join(', ') || 'No categories configured'}</span></div><div><strong>Upload policy</strong><span>{uploadPolicy ? `${uploadPolicy.policy.version} · ${uploadPolicy.policy_digest} · maximum ${Math.round(uploadPolicy.policy.max_file_size_bytes / 1024 / 1024)} MiB · ${uploadPolicy.policy.allowed_file_types.map((item) => item.extensions.join('/')).join(', ')}` : uploadPolicyError ? `Unavailable: ${uploadPolicyError}` : 'Loading policy…'}</span></div><div><strong>Review-priority policy</strong><span>{priorityPolicy ? `${priorityPolicy.policy.version} · ${priorityPolicy.policy_digest}` : priorityPolicyError ? `Unavailable: ${priorityPolicyError}` : 'Loading policy…'}</span></div><div><strong>Notifications and external verification</strong><span>Not implemented. No external messages or bank confirmations are sent.</span></div></div><p className="settings-readonly">Policy files are not editable here. Workflow, upload, graph, and priority policies are validated by the backend. Sessions use expiring HttpOnly cookies and server-side revocation; secure-cookie mode must be enabled when serving over HTTPS. This local prototype has not undergone an independent security review and must not be exposed publicly.</p></section>}
    {page === 'settings' && user.system_admin && <UserAdministration institutions={institutions} currentUser={user} />}
    {page === 'settings' && !user.system_admin && <section className="panel dashboard-state"><strong>Account administration unavailable</strong><span>Only system administrators can provision accounts, assign institution roles, reset passwords, or deactivate users.</span></section>}
    {!['dashboard', 'institutions', 'fdr-records', 'documents', 'relationships', 'review-queue', 'audit-trail', 'settings'].includes(page) && <section className="panel dashboard-state" role="alert"><strong>Page not found</strong><span>The requested local DepositGuard page does not exist.</span></section>}
    {['dashboard', 'institutions', 'fdr-records', 'documents', 'relationships', 'review-queue', 'audit-trail', 'settings'].includes(page) && <section className="panel live-workspace" id="fdr-workspace">
      <div className="panel-heading live-workspace-heading"><div><h2>{page === 'institutions' ? 'Institution selection' : 'Selected institution context'}</h2><p>Institution and FDR selections remain available while navigating.</p></div><span className="queue-source queue-live">BACKEND WORKSPACE</span></div>
      {page === 'documents' && !recordId && <div className="queue-state" role="status"><div><strong>{!institutionId ? 'Select an institution first' : recordsView === 'empty' ? 'No FDR record is available yet' : recordsView === 'error' ? 'FDR records could not be loaded' : 'Select an FDR record to manage documents'}</strong><span>{!institutionId ? 'Select one of your authorized institutions above.' : recordsView === 'empty' ? 'An institution administrator can create the first record on the FDR Records page.' : recordsView === 'error' ? 'Retry the FDR record list above, then select a record.' : 'Document upload, version history, integrity checks, and evidence history appear after you select a record.'}</span></div></div>}
      {hasConfigurationReadError && <div className="workspace-inline-error"><AlertCircle size={15} /> {workflowError && `Workflow configuration unavailable: ${workflowError}. `}{graphPolicyError && `Graph policy unavailable: ${graphPolicyError}. `}<button className="text-button" onClick={() => setInstitutionRetry((value) => value + 1)} disabled={institutionLoading || busy}>Retry configuration reads</button></div>}
      <div className="workspace-setup-grid">
        <label className="workspace-field"><span>Institution</span><select value={institutionId} onChange={(event) => { const nextId = event.target.value; setInstitutionId(nextId); onInstitutionChange(nextId); setRecordId(''); setRecords([]); setRecordsLoading(Boolean(nextId)); setRecordsError(''); setDetail(emptyDetail); setSearchMessage(''); setConfiguredInstitutionMessage('') }} disabled={institutionLoading || busy}>
          <option value="">{institutionLoading ? 'Loading institutions…' : 'Choose an institution'}</option>
          {institutions.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.id}</option>)}
        </select></label>
        <div className="workspace-identity"><span>Signed in as</span><strong>{user.display_name}</strong><small>{user.email} · {role?.replace(/_/g, ' ') ?? 'select an institution'}</small></div>
      </div>
      {configuredInstitutionMessage && <div className="workspace-inline-error">{configuredInstitutionMessage}</div>}
      {searchMessage && <div className={searchMessage.startsWith('No FDR') || searchMessage.startsWith('Choose') || searchMessage.startsWith('Search is unavailable') ? 'workspace-inline-error' : 'workspace-action-notice'} role="status">{searchMessage}</div>}
      {institutionError && <div className="workspace-inline-error"><AlertCircle size={15} /> API unavailable: {institutionError}<button className="text-button" onClick={() => setInstitutionRetry((value) => value + 1)} disabled={institutionLoading || busy}>Retry</button></div>}
      {page === 'institutions' && !institutionLoading && <div className="workspace-create-panel"><div><strong>{canCreateInstitution ? (institutions.length ? 'Create another local institution' : 'Create a local institution') : 'Institution access'}</strong><span>{canCreateInstitution ? 'Account provisioning and institution creation are restricted to system administrators.' : 'Your institution memberships determine which records appear here. Contact a system administrator to change access.'}</span></div>
        {canCreateInstitution && <form onSubmit={createInstitution} className="workspace-form-inline"><input aria-label="Institution name" value={institutionName} onChange={(event) => setInstitutionName(event.target.value)} placeholder="Institution name" maxLength={200} required /><button className="button button-primary" disabled={busy}><Plus size={15} /> Create institution</button></form>}
      </div>}
      {!institutionLoading && !user.system_admin && institutions.length === 0 && (
        <div className="queue-state" role="status">
          <div>
            <strong>No institution assigned</strong>
            <span>Your account currently has no institution memberships assigned. To view or manage FDR records and documents, a system administrator must assign your account to an authorized institution from Account Settings.</span>
          </div>
        </div>
      )}
      {institutionId && <>
        <div className="workspace-record-row">
          <label className="workspace-field record-picker"><span>FDR record</span><select value={recordId} onChange={(event) => setRecordId(event.target.value)} disabled={recordsLoading || busy}>
            <option value="">{recordsView === 'loading' ? 'Loading records…' : recordsView === 'error' ? 'Record list unavailable' : recordsView === 'ready' ? 'Choose a record' : 'No records yet'}</option>
            {records.map((item) => <option key={item.id} value={item.id}>{item.id}{item.instrument_reference ? ` · ${item.instrument_reference}` : ''} · ${item.workflow_stage}</option>)}
          </select></label>
          <span className="workspace-record-count">{recordsLoading ? 'Loading…' : recordsError ? 'Record count unavailable' : `${records.length} local record(s)`}</span>
        </div>
        {recordsError && <div className="workspace-inline-error"><AlertCircle size={15} /> {recordsError}<button className="text-button" onClick={() => setRecordsRetry((value) => value + 1)} disabled={recordsLoading || busy}>Retry</button></div>}
        {page === 'fdr-records' && recordsView === 'empty' && <div className="workspace-create-panel"><div><strong>{canManageRecords ? 'Create an FDR record' : 'No FDR records'}</strong><span>{canManageRecords ? 'Record stage and ownership are assigned by the backend.' : 'Your current role is read only for record creation. Contact an institution administrator.'}</span></div>
          {canManageRecords && <form onSubmit={createRecord} className="workspace-form-inline"><input aria-label="Optional instrument reference" value={instrumentReference} onChange={(event) => setInstrumentReference(event.target.value)} placeholder="Optional synthetic instrument reference" maxLength={120} /><button className="button button-primary" disabled={busy}><Plus size={15} /> Create record</button></form>}
        </div>}
        {page === 'fdr-records' && !!records.length && (canManageRecords ? <form onSubmit={createRecord} className="workspace-new-record"><input aria-label="Optional instrument reference" value={instrumentReference} onChange={(event) => setInstrumentReference(event.target.value)} placeholder="Optional synthetic reference for a new record" maxLength={120} /><button className="text-button" disabled={busy}><Plus size={14} /> New FDR record</button></form> : <p className="detail-empty">Your role allows read-only access to FDR records.</p>)}
      </>}
      {(actionError || actionNotice) && <div className={`${actionError ? 'workspace-inline-error' : 'workspace-inline-success'} workspace-feedback-toast`} role="status" aria-live={actionError ? 'assertive' : 'polite'}>{actionError || actionNotice}</div>}
    </section>}

    {page === 'review-queue' && <ReviewQueuePanel institutionId={institutionId} refreshKey={refreshToken} />}
    {page === 'relationships' && <RelationshipExplorer institutionId={institutionId} recordId={recordId} refreshKey={refreshToken} />}

    {institutionId && recordId && ['fdr-records', 'documents', 'relationships', 'review-queue', 'audit-trail'].includes(page) && <section className="live-record-detail" aria-label="Selected FDR record details">
      {detail.loading && <div className="panel queue-state">Loading record, document versions, audit, and evidence…</div>}
      {!detail.loading && hasDetailReadError && <div className="panel workspace-inline-error" role="alert"><AlertCircle size={15} /> One or more selected-record reads failed. Refresh to retry failed details and version histories.<button className="text-button" onClick={() => setRefreshToken((value) => value + 1)} disabled={busy}>Retry record details</button></div>}
      {detail.recordError && <div className="panel workspace-inline-error"><AlertCircle size={15} /> Record detail unavailable: {detail.recordError}</div>}
      {detail.record && <>
        {page === 'fdr-records' && <section className="panel record-summary">
          <div className="panel-heading"><div><h2>{detail.record.instrument_reference || 'FDR record'}</h2><p className="record-id">{detail.record.id}</p></div><span className="stage-badge">{detail.record.workflow_stage.replace(/_/g, ' ')}</span></div>
          <div className="record-summary-meta"><span>Created {dateText(detail.record.created_at)}</span><span>Updated {dateText(detail.record.updated_at)}</span></div>
          {availableTransitions.length > 0 && canTransition && <form className="transition-form" onSubmit={transitionRecord}>
            <label className="workspace-field"><span>Available workflow transition</span><select required value={targetStage} onChange={(event) => setTargetStage(event.target.value)}><option value="">Choose next stage</option>{availableTransitions.map((item) => <option key={`${item.from_stage}-${item.to_stage}`} value={item.to_stage}>{workflow?.stages.find((stage) => stage.key === item.to_stage)?.label ?? item.to_stage}</option>)}</select></label>
            <input aria-label="Transition reason" value={transitionReason} onChange={(event) => setTransitionReason(event.target.value)} placeholder="Optional reason" maxLength={1000} />
            <button className="button button-secondary" disabled={busy || !targetStage}><Workflow size={14} /> Apply transition</button>
          </form>}
          {availableTransitions.length > 0 && !canTransition && <p className="detail-empty">Your role can review this record but cannot perform workflow transitions.</p>}
          {workflowError && <div className="workspace-inline-error">Workflow configuration unavailable: {workflowError}</div>}
        </section>}

        <div className="detail-columns">
          {page === 'documents' && <section className="panel detail-panel" id="record-documents">
            <div className="panel-heading"><div><h2>Documents and versions</h2><p>Private files with immutable version metadata</p></div><FileUp size={17} className="detail-heading-icon" /></div>
            {detail.documentError && <div className="workspace-inline-error">{detail.documentError}</div>}
            {!detail.documentError && detail.documents.length === 0 && <p className="detail-empty">No documents are recorded for this FDR.</p>}
            <div className="document-list">{detail.documents.map((document) => <details className="document-card" key={document.id} open>
              <summary className="document-card-heading"><span><strong>{document.category_key.replace(/_/g, ' ')}</strong><small>{document.latest_version?.original_filename ?? 'No upload version'}</small></span><small>Document {document.id} · {document.versions?.length ?? 0} version(s)</small></summary>
              {document.versions_error && <div className="workspace-inline-error">Version history unavailable: {document.versions_error}</div>}
              {!document.versions_error && !document.versions?.length && <p className="detail-empty">No versions are available for this document.</p>}
              {(document.versions ?? []).map((version) => <div className="version-row" key={version.id}>
                <div><strong>Version {version.version_number}</strong><span>{version.original_filename} · {version.byte_size.toLocaleString()} bytes · {version.media_type}</span><span>Uploaded {dateText(version.uploaded_at)} · by {version.uploaded_by}</span><span>Workflow {version.configuration_version} · Upload policy {version.upload_policy_version ?? 'not recorded'}</span><code>Version ID {version.id}</code><code>{version.digest_algorithm.toUpperCase()} {version.sha256_digest}</code></div>
                {canCheckIntegrity ? <button className="text-button" onClick={() => runIntegrityCheck(document.id, version.id)} disabled={busy}><SearchCheck size={14} /> Check integrity</button> : <span className="permission-note">Integrity checks are unavailable for your role.</span>}
              </div>)}
            </details>)}</div>
            <div className="document-upload-form">
              <label className="workspace-field"><span>Configured document category</span>{workflow?.document_requirements.length ? <select value={categoryKey} onChange={(event) => setCategoryKey(event.target.value)}>{workflow.document_requirements.map((item) => <option key={item.key} value={item.key}>{item.label} {item.required ? '· required by local config' : ''}</option>)}</select> : <input value={categoryKey} onChange={(event) => setCategoryKey(event.target.value)} placeholder="Category key" />}</label>
              <label className="workspace-field"><span>Version target</span><select value={versionDocumentId} onChange={(event) => setVersionDocumentId(event.target.value)}><option value="">Create a new document</option>{detail.documents.filter((item) => item.category_key === categoryKey).map((item) => <option key={item.id} value={item.id}>Add version to {item.id}</option>)}</select></label>
              <input key={fileInputKey} aria-label="Document file" type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(event) => setUploadFile(event.target.files?.[0])} disabled={!canUpload || busy} />
              <button className="button button-primary" onClick={upload} disabled={!canUpload || busy || !institutionId || !recordId || !uploadFile || !categoryKey}><FileUp size={14} /> {busy ? 'Saving…' : 'Upload document'}</button>
              {!canUpload && <p className="permission-note" role="note">Upload is available to institution administrators and document officers. Your role can view document history.</p>}
            </div>
            <p className="detail-security-note">The integrity result compares stored bytes with the upload-time digest only; it does not verify authenticity or a bank record.</p>
          </section>}

          {page === 'review-queue' && <section className="panel detail-panel" id="record-priority">
            <div className="panel-heading"><div><h2>Current advisory priority</h2><p>Calculated from current backend inputs</p></div><span className="queue-source queue-live">LIVE API</span></div>
            {detail.scoreError && <div className="workspace-inline-error">Priority score unavailable: {detail.scoreError}</div>}
            {detail.score && <><div className="detail-score-row"><strong>{detail.score.score}<small>/100</small></strong><span>{detail.score.priority_category_label}</span></div><p className="score-meta">Policy {detail.score.policy_version} · Workflow config {detail.score.workflow_config_version} · {dateText(detail.score.calculated_at)}</p>
              <div className="score-factor-list">{detail.score.factors.map((factor) => <article key={factor.factor}><strong>{factor.factor.replace(/_/g, ' ')} <span>+{factor.points}</span></strong><p>{factor.explanation}</p>{factor.missing_inputs.map((item) => <small key={item}>{item}</small>)}</article>)}</div>
              {detail.score.missing_inputs.length > 0 && <div className="missing-input-list"><strong>Missing or unevaluated inputs</strong>{detail.score.missing_inputs.map((item) => <span key={item}>{item}</span>)}</div>}
              <p className="detail-security-note">Advisory only. This score is not a fraud probability and does not approve or release an FDR.</p>
            </>}
          </section>}

          {page === 'documents' && <section className="panel detail-panel" id="record-evidence">
            <div className="panel-heading"><div><h2>Evidence and integrity history</h2><p>Results remain linked to the exact version checked</p></div><FileCheck2 size={17} className="detail-heading-icon" /></div>
            {detail.evidenceError && <div className="workspace-inline-error">{detail.evidenceError}</div>}
            {!detail.evidenceError && detail.evidence.length === 0 && <p className="detail-empty">No evidence checks have been recorded.</p>}
            <div className="evidence-list">{detail.evidence.map((item) => {
              const recordedDigest = item.result_details.recorded_sha256
              const observedDigest = item.result_details.observed_sha256
              return <article className="evidence-card" key={item.id}>
                <div className="evidence-card-heading"><strong>{item.check_type.replace(/_/g, ' ')}</strong><span className={`integrity-status integrity-${item.result_status.toLowerCase()}`}>{item.result_status}</span></div>
                <p>{item.explanation}</p><small>Version ID {item.document_version_id ?? 'not linked'} · {dateText(item.executed_at)}</small>
                {typeof recordedDigest === 'string' && <small>Recorded SHA-256 {recordedDigest}</small>}
                {typeof observedDigest === 'string' && <small>Observed SHA-256 {observedDigest}</small>}
                {observedDigest === null && <small>Observed SHA-256 unavailable</small>}
                <small>Software {item.software_version ?? 'not recorded'} · Rule {item.rule_version ?? 'not recorded'}</small>
              </article>
            })}</div>
          </section>}

          {page === 'relationships' && <section className="panel detail-panel" id="record-relationships">
            <div className="panel-heading"><div><h2>Recorded FDR relationships</h2><p>Explicit same-institution associations</p></div><RefreshCw size={16} className="detail-heading-icon" /></div>
            {detail.relationshipError && <div className="workspace-inline-error">{detail.relationshipError}</div>}
            {!detail.relationshipError && detail.relationships.length === 0 && <p className="detail-empty">No FDR-to-FDR relationships recorded.</p>}
            <div className="relationship-list">{detail.relationships.map((item) => <article key={item.id} className="relationship-row"><strong>{item.relationship_label}</strong><span>{item.source_record_id} → {item.target_record_id}</span><small>{item.review_status.replace(/_/g, ' ')} · {item.note || 'No note'}</small></article>)}</div>
            {canManageRelationships && <form className="relationship-form" onSubmit={createRelationship}>
              <label className="workspace-field"><span>Related FDR record</span><select value={relationshipTarget} onChange={(event) => setRelationshipTarget(event.target.value)}><option value="">Choose record</option>{records.filter((item) => item.id !== recordId).map((item) => <option key={item.id} value={item.id}>{item.instrument_reference || item.id}</option>)}</select></label>
              <label className="workspace-field"><span>Configured relationship</span><select value={relationshipType} onChange={(event) => setRelationshipType(event.target.value)}><option value="">Choose type</option>{graphPolicy?.relationship_types.map((item) => <option key={item.key} value={item.key}>{item.label} · {item.key}{item.allow_cycles ? ' · cycles allowed' : ' · cycle blocked'}</option>)}</select></label>
              {graphPolicyError && <div className="workspace-inline-error">Graph policy unavailable: {graphPolicyError}</div>}
              <input aria-label="Relationship note" value={relationshipNote} onChange={(event) => setRelationshipNote(event.target.value)} placeholder="Optional recorded note" maxLength={500} />
              <button className="button button-secondary" disabled={busy || !relationshipTarget || !relationshipType}><Plus size={14} /> Record relationship</button>
            </form>}
            {!canManageRelationships && <p className="permission-note">Relationship creation is not permitted for your role. Existing relationships remain visible.</p>}
          </section>}

          {page === 'audit-trail' && <section className="panel detail-panel" id="record-history">
            <div className="panel-heading"><div><h2>Workflow and audit history</h2><p>Lifecycle events recorded for this FDR</p></div><Workflow size={17} className="detail-heading-icon" /></div>
            {detail.auditError && <div className="workspace-inline-error">{detail.auditError}</div>}
            {!detail.auditError && detail.audit.length === 0 && <p className="detail-empty">No audit events are recorded.</p>}
            <div className="audit-list">{detail.audit.map((item) => <article key={item.id} className="audit-row"><span className="audit-dot" /><div><strong>{item.event_type.replace(/_/g, ' ')}</strong><span>{item.from_stage && item.to_stage ? `${item.from_stage} → ${item.to_stage}` : item.reason || 'Recorded event'}</span><small>{dateText(item.created_at)} · actor reference {item.actor_id} (historical IDs may be unverified) · config {item.configuration_version ?? 'unversioned'}</small></div></article>)}</div>
          </section>}
        </div>
      </>}
    </section>}
  </>
}
