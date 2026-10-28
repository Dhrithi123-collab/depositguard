import { useEffect, useState } from 'react';
import { api, type ManagedUser } from '../services/api';
import { Link } from 'react-router-dom';
import { ShieldCheck } from 'lucide-react';

export function AdminUserApprovalScreen() {
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadPending = async () => {
    setLoading(true);
    setError('');
    try {
      const all = await api.listUsers();
      const pending = all.filter((u) => !u.active);
      setUsers(pending);
    } catch (e) {
      setError('Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadPending();
  }, []);

  const approve = async (id: string) => {
    try {
      await api.setUserActive(id, true);
      await loadPending();
    } catch (e) {
      setError('Failed to approve user');
    }
  };

  const reject = async (id: string) => {
    try {
      await api.setUserActive(id, false);
      await loadPending();
    } catch (e) {
      setError('Failed to reject user');
    }
  };

  if (loading) return <div className="auth-page"><div className="auth-card" role="status">Loading pending users…</div></div>;

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="auth-brand">
          <span><ShieldCheck size={22} /></span>
          <div>
            <strong>DepositGuard</strong>
            <small>ADMIN USER APPROVAL</small>
          </div>
        </div>
        <h1>Pending Registrations</h1>
        {error && <div className="auth-error" role="alert">{error}</div>}
        {users.length === 0 ? (
          <p>No pending users.</p>
        ) : (
          <table className="full-width-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left' }}>Name</th>
                <th style={{ textAlign: 'left' }}>Email</th>
                <th style={{ textAlign: 'left' }}>Institution / Role</th>
                <th style={{ textAlign: 'center' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} style={{ borderBottom: '1px solid #ccc' }}>
                  <td>{u.display_name}</td>
                  <td>{u.email}</td>
                  <td>{u.memberships.map(m => `${m.institution_id}:${m.role}`).join(', ') || 'N/A'}</td>
                  <td style={{ textAlign: 'center' }}>
                    <button className="button button-primary" onClick={() => approve(u.id)} style={{ marginRight: '0.5rem' }}>Approve</button>
                    <button className="button" onClick={() => reject(u.id)}>Reject</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="auth-footnote"><Link to="/">← Back to dashboard</Link></p>
      </section>
    </main>
  );
}
