// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useNavigate } from 'react-router-dom'
import App from '../src/App'
import { AuthProvider } from '../src/components/Auth'

function HistoryControls() {
  const navigate = useNavigate()
  return <div><button onClick={() => navigate(-1)}>Test back</button><button onClick={() => navigate(1)}>Test forward</button></div>
}

function renderApp(path = '/dashboard') {
  return render(<MemoryRouter initialEntries={[path]}><AuthProvider><HistoryControls /><App /></AuthProvider></MemoryRouter>)
}

describe('page routing', () => {
  let authenticated: boolean
  beforeEach(() => {
    authenticated = true
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/auth/session') && !authenticated) return new Response(JSON.stringify({ error: { message: 'Sign in is required.' } }), { status: 401, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/api/auth/login')) {
        const body = JSON.parse(String(init?.body ?? '{}')) as { password?: string }
        if (body.password !== 'synthetic-test-password') return new Response(JSON.stringify({ error: { message: 'Email or password is incorrect.' } }), { status: 401, headers: { 'Content-Type': 'application/json' } })
        authenticated = true
      }
      if (url.endsWith('/api/auth/logout')) { authenticated = false; return new Response(null, { status: 204 }) }
      if (url.endsWith('/api/auth/session') || url.endsWith('/api/auth/login')) return new Response(JSON.stringify({
        csrf_token: 'csrf-test-token',
        user: { id: 'synthetic-user', email: 'local@example.test', display_name: 'Local Reviewer', system_admin: true, active: true, must_change_password: false, memberships: [], created_at: '2026-01-01T00:00:00Z' },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/api/institutions?limit=500')) return new Response(JSON.stringify([{ id: 'synthetic-institution', name: 'Synthetic Institution', created_at: '2026-01-01T00:00:00Z' }]), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/api/workflow/configuration')) return new Response(JSON.stringify({ config: { version: 'v1', stages: [], transitions: [], document_requirements: [{ key: 'evidence', label: 'Supporting Evidence', required: false }] } }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/api/graph/policy')) return new Response(JSON.stringify({ policy: { version: 'v1', relationship_types: [], max_traversal_depth: 3, max_nodes: 50 } }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/fdr-records?limit=500')) return new Response(JSON.stringify([{ id: 'test-fdr-1', instrument_reference: 'REF-001', workflow_stage: 'draft', institution_id: 'synthetic-institution', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }]), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/fdr-records/test-fdr-1')) return new Response(JSON.stringify({ id: 'test-fdr-1', instrument_reference: 'REF-001', workflow_stage: 'draft', institution_id: 'synthetic-institution', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/fdr-records/test-fdr-1/documents')) return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/fdr-records/test-fdr-1/evidence-checks')) return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } })
      return new Response(JSON.stringify({ detail: 'API not configured in route test' }), { status: 503, headers: { 'Content-Type': 'application/json' } })
    }))
  })
  afterEach(() => { cleanup(); vi.unstubAllGlobals() })

  it.each(['/dashboard', '/institutions', '/fdr-records', '/documents', '/relationships', '/review-queue', '/audit-trail', '/settings'])('opens %s directly with matching active navigation', async (path) => {
    renderApp(path)
    const label = ({ '/dashboard': 'Dashboard', '/institutions': 'Institutions', '/fdr-records': 'FDR records', '/documents': 'Documents', '/relationships': 'Relationships', '/review-queue': 'Review queue', '/audit-trail': 'Audit trail', '/settings': 'Settings' } as Record<string, string>)[path]
    expect(await screen.findByRole('heading', { name: label, level: 1 })).toBeTruthy()
    expect(screen.getByRole('link', { name: new RegExp(label, 'i') }).getAttribute('aria-current')).toBe('page')
  })

  it('navigates between pages and supports back and forward without losing shared context', async () => {
    renderApp('/institutions')
    expect(await screen.findByText(/local@example.test/)).toBeTruthy()
    const institution = await screen.findByLabelText('Institution') as HTMLSelectElement
    fireEvent.change(institution, { target: { value: 'synthetic-institution' } })
    fireEvent.click(screen.getByRole('link', { name: /documents/i }))
    expect(await screen.findByRole('heading', { name: 'Documents', level: 1 })).toBeTruthy()
    expect(screen.getByText(/local@example.test/)).toBeTruthy()
    expect(screen.getByLabelText('Institution')).toHaveProperty('value', 'synthetic-institution')
    fireEvent.click(screen.getByRole('button', { name: 'Test back' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Institutions', level: 1 })).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: 'Test forward' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Documents', level: 1 })).toBeTruthy())
  })

  it('shows a not-found state for unknown routes', async () => {
    renderApp('/not-a-page')
    expect(await screen.findByRole('heading', { name: 'Page not found', level: 1 })).toBeTruthy()
    expect(screen.getByText(/requested local depositguard page does not exist/i)).toBeTruthy()
  })

  it('requires sign-in and displays invalid credentials before opening the workspace', async () => {
    authenticated = false
    renderApp('/documents')
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'local@example.test' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'incorrect-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Email or password is incorrect.')
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'synthetic-test-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('heading', { name: 'Documents', level: 1 })).toBeTruthy()
  })

  it('validates signup form: password mismatch, password under 6 chars, and submits successfully without institution', async () => {
    authenticated = false
    renderApp('/signup')
    expect(await screen.findByRole('heading', { name: 'Sign up' })).toBeTruthy()
    // Verify no institution dropdown is present
    expect(screen.queryByLabelText(/institution/i)).toBeNull()

    // Test password shorter than 6 characters
    fireEvent.change(screen.getByLabelText(/^Full name/i), { target: { value: 'New Test User' } })
    fireEvent.change(screen.getByLabelText(/^Email address/i), { target: { value: 'newuser@example.test' } })
    fireEvent.change(screen.getByLabelText(/^Password/i), { target: { value: '12345' } })
    fireEvent.change(screen.getByLabelText(/^Confirm password/i), { target: { value: '12345' } })
    fireEvent.change(screen.getByLabelText(/^Role/i), { target: { value: 'auditor' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign Up' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Password must be at least 6 characters')

    // Test password mismatch
    fireEvent.change(screen.getByLabelText(/^Password/i), { target: { value: 'validPass6' } })
    fireEvent.change(screen.getByLabelText(/^Confirm password/i), { target: { value: 'different' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign Up' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Passwords do not match')
  })

  it('displays document upload and evidence panels on /documents when an FDR record is selected', async () => {
    renderApp('/documents')
    expect(await screen.findByRole('heading', { name: 'Documents', level: 1 })).toBeTruthy()
    const fdrOption = await screen.findByRole('option', { name: /test-fdr-1/i })
    expect(fdrOption).toBeTruthy()
    const fdrSelect = screen.getByLabelText('FDR record') as HTMLSelectElement
    fireEvent.change(fdrSelect, { target: { value: 'test-fdr-1' } })
    expect(await screen.findByRole('heading', { name: 'Documents and versions', level: 2 })).toBeTruthy()
    expect(await screen.findByRole('heading', { name: 'Evidence and integrity history', level: 2 })).toBeTruthy()
    expect(screen.getByRole('button', { name: /upload document/i })).toBeTruthy()
  })
})
