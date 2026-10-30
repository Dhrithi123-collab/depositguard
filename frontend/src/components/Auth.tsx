import { createContext, useContext, useEffect, useState, type FormEvent, type ReactNode } from 'react'

import { Link, useNavigate } from 'react-router-dom'
import { LogIn, ShieldCheck } from 'lucide-react'
import { ApiError, api, setCsrfToken, type AuthSession } from '../services/api'

type AuthState = {
  loading: boolean
  session?: AuthSession
  error: string
  login: (email: string, password: string) => Promise<void>
  register: (payload: { email: string; display_name: string; password: string; role: string; institution_id?: string | null }) => Promise<void>
  logout: () => Promise<void>
  changePassword: (current: string, next: string) => Promise<void>
}
const AuthContext = createContext<AuthState | undefined>(undefined)
const errorMessage = (error: unknown) => error instanceof ApiError ? error.message : error instanceof Error ? error.message : 'The request could not be completed.'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession>()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    api.session().then((value) => {
      if (!active) return
      setSession(value); setCsrfToken(value.csrf_token)
    }).catch(() => {
      if (active) { setSession(undefined); setCsrfToken('') }
    }).finally(() => { if (active) setLoading(false) })
    const unauthorize = () => { setSession(undefined); setCsrfToken(''); setError('Your session expired. Sign in again.') }
    window.addEventListener('depositguard:unauthorized', unauthorize)
    return () => { active = false; window.removeEventListener('depositguard:unauthorized', unauthorize) }
  }, [])

  const login = async (email: string, password: string) => {
    setError('')
    try {
      const value = await api.login(email, password)
      setSession(value); setCsrfToken(value.csrf_token)
    } catch (reason) { const message = errorMessage(reason); setError(message); throw new Error(message) }
  }
  const register = async (payload: { email: string; display_name: string; password: string; role: string; institution_id?: string | null }) => {
    setError('')
    try {
      const value = await api.registerUser(payload)
      setSession(value); setCsrfToken(value.csrf_token)
    } catch (reason) { const message = errorMessage(reason); setError(message); throw new Error(message) }
  }
  const logout = async () => {
    setError('')
    try {
      await api.logout()
      setSession(undefined); setCsrfToken('')
    } catch (reason) { const message = errorMessage(reason); setError(message); throw new Error(message) }
  }
  const changePassword = async (current: string, next: string) => {
    setError('')
    try {
      await api.changePassword(current, next)
      const value = await api.session()
      setSession(value); setCsrfToken(value.csrf_token)
    } catch (reason) { const message = errorMessage(reason); setError(message); throw new Error(message) }
  }
  return <AuthContext.Provider value={{ loading, session, error, login, register, logout, changePassword }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider.')
  return value
}

export function SignInScreen() {
  const { login, error } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [pending, setPending] = useState(false);
  const [formError, setFormError] = useState('');
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setPending(true);
    setFormError('');
    try {
      await login(email, password);
    } catch (reason) {
      setFormError(errorMessage(reason));
    } finally {
      setPending(false);
    }
  };
  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="auth-brand"><span><ShieldCheck size={22} /></span><div><strong>DepositGuard</strong><small>LOCAL ASSURANCE WORKSPACE</small></div></div>
        <h1>Sign in</h1>
        <p>Use an account provisioned by your DepositGuard administrator.</p>
        {(formError || error) && <div className="auth-error" role="alert">{formError || error}</div>}
        <form onSubmit={submit} className="auth-form">
          <label>Email address<input type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required maxLength={254} /></label>
          <label>Password<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required maxLength={128} /></label>
          <button className="button button-primary" disabled={pending}><LogIn size={16} />{pending ? 'Signing in…' : 'Sign in'}</button>
        </form>
        <p className="auth-footnote"><Link to="/signup">Create an account</Link></p>
      </section>
    </main>
  );
}

export function PasswordChangeScreen() {
  const { session, changePassword, logout } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError('')
    if (next !== confirm) { setError('The new passwords do not match.'); return }
    setPending(true)
    try { await changePassword(current, next) } catch (reason) { setError(errorMessage(reason)) } finally { setPending(false) }
  }
  return <main className="auth-page"><section className="auth-card">
    <div className="auth-brand"><span><ShieldCheck size={22} /></span><div><strong>DepositGuard</strong><small>ACCOUNT SECURITY</small></div></div>
    <h1>Change your temporary password</h1><p>Set a new password before continuing, {session?.user.display_name}.</p>
    {error && <div className="auth-error" role="alert">{error}</div>}
    <form onSubmit={submit} className="auth-form">
      <label>Current password<input type="password" autoComplete="current-password" value={current} onChange={(event) => setCurrent(event.target.value)} required /></label>
      <label>New password<input type="password" autoComplete="new-password" value={next} onChange={(event) => setNext(event.target.value)} minLength={6} maxLength={128} required /><small>Use 6–128 characters.</small></label>
      <label>Confirm new password<input type="password" autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} minLength={6} maxLength={128} required /></label>
      <button className="button button-primary" disabled={pending}>{pending ? 'Saving…' : 'Update password'}</button>
    </form>
    <button className="text-button" onClick={() => void logout().catch(() => undefined)}>Sign out instead</button>
  </section></main>
}

export function SignUpScreen() {
  const navigate = useNavigate();
  const { register } = useAuth();
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [role, setRole] = useState('');
  const [pending, setPending] = useState(false);
  const [formError, setFormError] = useState('');

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setFormError('');
    if (password.length < 6) return setFormError('Password must be at least 6 characters');
    if (password !== confirm) return setFormError('Passwords do not match');
    if (!role) return setFormError('Please select a role');
    setPending(true);
    try {
      await register({
        email,
        display_name: displayName,
        password,
        role,
      });
      // Established session automatically; navigate to /dashboard
      navigate('/dashboard');
    } catch (reason) {
      setFormError(errorMessage(reason));
    } finally {
      setPending(false);
    }
  };

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="auth-brand"><span><ShieldCheck size={22} /></span><div><strong>DepositGuard</strong><small>REGISTER ACCOUNT</small></div></div>
        <h1>Sign up</h1>
        {formError && <div className="auth-error" role="alert">{formError}</div>}
        <form onSubmit={submit} className="auth-form">
          <label>Full name<input type="text" value={displayName} onChange={e => setDisplayName(e.target.value)} required maxLength={120} /></label>
          <label>Email address<input type="email" value={email} onChange={e => setEmail(e.target.value)} required maxLength={254} /></label>
          <label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={6} maxLength={128} />
            <small>Use 6–128 characters.</small></label>
          <label>Confirm password<input type="password" value={confirm} onChange={e => setConfirm(e.target.value)} required minLength={6} maxLength={128} />
            <small>Use 6–128 characters.</small></label>
          <label>Role<select value={role} onChange={e => setRole(e.target.value)} required>
            <option value="">Select role</option>
            <option value="institution_admin">Institution Admin</option>
            <option value="document_officer">Document Officer</option>
            <option value="reviewer">Reviewer</option>
            <option value="approver">Approver</option>
            <option value="auditor">Auditor</option>
          </select></label>
          <button className="button button-primary" disabled={pending}>{pending ? 'Signing up…' : 'Sign Up'}</button>
        </form>
        <p className="auth-footnote"><Link to="/login">Already have an account? Sign in</Link></p>
      </section>
    </main>
  );
}
