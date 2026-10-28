import { useEffect, useState, type FormEvent } from 'react'
import { AlertCircle, Plus, RefreshCw, UserCog } from 'lucide-react'
import { ApiError, api, type AuthUser, type Institution, type ManagedUser } from '../services/api'

const roleChoices = [
  ['institution_admin', 'Institution administrator'], ['document_officer', 'Document officer'],
  ['reviewer', 'Reviewer'], ['approver', 'Approving authority'], ['auditor', 'Read-only auditor'],
]
const errorText = (error: unknown) => error instanceof ApiError ? error.message : error instanceof Error ? error.message : 'The API request could not be completed.'

export function UserAdministration({ institutions, currentUser }: { institutions: Institution[]; currentUser: AuthUser }) {
  const [users, setUsers] = useState<ManagedUser[]>([])
  const [loading, setLoading] = useState(true)
  const [retry, setRetry] = useState(0)
  const [error, setError] = useState('')
  const [busyUser, setBusyUser] = useState('')
  const [message, setMessage] = useState('')
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [temporaryPassword, setTemporaryPassword] = useState('')
  const [institutionId, setInstitutionId] = useState('')
  const [role, setRole] = useState('document_officer')
  const [systemAdmin, setSystemAdmin] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    api.listUsers().then((data) => { if (active) setUsers(data) })
      .catch((reason: unknown) => { if (active) setError(errorText(reason)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [retry])

  const create = async (event: FormEvent) => {
    event.preventDefault(); setBusyUser('create'); setError(''); setMessage('')
    try {
      const created = await api.createUser({
        email, display_name: displayName, temporary_password: temporaryPassword,
        system_admin: systemAdmin, institution_id: systemAdmin ? null : institutionId || null,
        role: systemAdmin ? null : role || null,
      })
      setUsers((current) => [created, ...current.filter((item) => item.id !== created.id)])
      setEmail(''); setDisplayName(''); setTemporaryPassword(''); setInstitutionId(''); setSystemAdmin(false)
      setMessage(`Account created for ${created.email}. The user must change the temporary password at first sign in.`)
    } catch (reason) { setError(errorText(reason)) } finally { setBusyUser('') }
  }

  const setActive = async (user: ManagedUser) => {
    setBusyUser(user.id); setError(''); setMessage('')
    try {
      const updated = await api.setUserActive(user.id, !user.active)
      setUsers((current) => current.map((item) => item.id === user.id ? updated : item))
    } catch (reason) { setError(errorText(reason)) } finally { setBusyUser('') }
  }

  const assign = async (event: FormEvent<HTMLFormElement>, user: ManagedUser) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setBusyUser(user.id); setError(''); setMessage('')
    try {
      const updated = await api.assignMembership(user.id, String(form.get('institution_id')), String(form.get('role')))
      setUsers((current) => current.map((item) => item.id === user.id ? updated : item))
      setMessage(`Institution role saved for ${user.email}.`)
    } catch (reason) { setError(errorText(reason)) } finally { setBusyUser('') }
  }

  const resetPassword = async (user: ManagedUser) => {
    const nextPassword = window.prompt(`Enter a temporary password for ${user.email} (6–128 characters). The user must change it at next sign in.`)
    if (nextPassword === null) return
    setBusyUser(user.id); setError(''); setMessage('')
    try {
      await api.resetUserPassword(user.id, nextPassword)
      setMessage(`Temporary password reset for ${user.email}; all their current sessions were revoked.`)
    } catch (reason) { setError(errorText(reason)) } finally { setBusyUser('') }
  }

  return <section className="panel user-admin-panel">
    <div className="panel-heading"><div><h2><UserCog size={17} /> User accounts and institution roles</h2><p>System-administrator controls. New accounts require a first-login password change.</p></div><button className="icon-button" onClick={() => setRetry((value) => value + 1)} aria-label="Refresh user list" disabled={loading}><RefreshCw size={14} /></button></div>
    {error && <div className="workspace-inline-error" role="alert"><AlertCircle size={15} />{error}</div>}
    {message && <p className="workspace-action-notice" role="status">{message}</p>}
    <form className="user-create-form" onSubmit={create}>
      <label className="workspace-field">Display name<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={120} required /></label>
      <label className="workspace-field">Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} maxLength={254} required /></label>
      <label className="workspace-field">Temporary password<input type="password" autoComplete="new-password" value={temporaryPassword} onChange={(event) => setTemporaryPassword(event.target.value)} minLength={6} maxLength={128} required /><small>6–128 characters; never shown again.</small></label>
      <label className="workspace-field">Role<select value={systemAdmin ? 'system_admin' : role} onChange={(event) => { const value = event.target.value; setSystemAdmin(value === 'system_admin'); if (value !== 'system_admin') setRole(value) }}><option value="system_admin">System administrator</option>{roleChoices.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      {!systemAdmin && <label className="workspace-field">Institution<select value={institutionId} onChange={(event) => setInstitutionId(event.target.value)} required><option value="">Choose institution</option>{institutions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
      <button className="button button-primary" disabled={Boolean(busyUser) || (!systemAdmin && !institutionId)}><Plus size={15} />{busyUser === 'create' ? 'Creating…' : 'Create account'}</button>
    </form>
    <div className="admin-user-list">
      {loading && <div className="queue-state" role="status">Loading user accounts…</div>}
      {!loading && !error && !users.length && <p className="detail-empty">No accounts are available.</p>}
      {!loading && users.map((user) => <article className="admin-user-row" key={user.id}>
        <div className="admin-user-main"><strong>{user.display_name}</strong><span>{user.email} · {user.system_admin ? 'System administrator' : user.memberships.map((membership) => `${membership.role.replace(/_/g, ' ')} · ${institutions.find((item) => item.id === membership.institution_id)?.name ?? membership.institution_id}`).join('; ') || 'No institution role'}</span><small>{user.active ? 'Active' : 'Deactivated'}{user.must_change_password ? ' · password change required' : ''}</small></div>
        <div className="admin-user-actions">
          {!user.system_admin && institutions.length > 0 && <form onSubmit={(event) => void assign(event, user)}><select aria-label={`Institution for ${user.email}`} name="institution_id" defaultValue={institutions[0].id}>{institutions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><select aria-label={`Role for ${user.email}`} name="role" defaultValue={user.memberships[0]?.role ?? 'document_officer'}>{roleChoices.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><button className="text-button" disabled={busyUser === user.id}>Save role</button></form>}
          <button className="text-button" onClick={() => void resetPassword(user)} disabled={busyUser === user.id}>Reset password</button>
          <button className="text-button" onClick={() => void setActive(user)} disabled={busyUser === user.id || user.id === currentUser.id || (user.system_admin && user.active)}>{user.active ? 'Deactivate' : 'Reactivate'}</button>
        </div>
      </article>)}
    </div>
    <p className="detail-security-note">Role changes and account lifecycle changes are recorded in the security audit log. Only a system administrator can provision accounts or assign institution roles.</p>
  </section>
}
