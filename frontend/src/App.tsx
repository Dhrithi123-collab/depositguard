import { useCallback, useState, type FormEvent } from 'react';
import { ArrowDownToLine, CircleHelp, Search } from 'lucide-react';
import { Link, useLocation, Navigate } from 'react-router-dom';
import { FdrWorkspace } from './components/FdrWorkspace';
import { Sidebar } from './components/Sidebar';
import { PasswordChangeScreen, SignInScreen, SignUpScreen, useAuth } from './components/Auth';
import { PendingApprovalScreen } from './components/PendingApprovalScreen';
import { AdminUserApprovalScreen } from './components/AdminUserApproval';

const pageTitles: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/institutions': 'Institutions',
  '/fdr-records': 'FDR records',
  '/documents': 'Documents',
  '/relationships': 'Relationships',
  '/review-queue': 'Review queue',
  '/audit-trail': 'Audit trail',
  '/settings': 'Settings',
};

function App() {
  const [search, setSearch] = useState('');
  const [institutionId, setInstitutionId] = useState('');
  const [overviewRefresh, setOverviewRefresh] = useState(0);
  const location = useLocation();
  const auth = useAuth();
  const title = pageTitles[location.pathname] ?? 'Page not found';
  const onInstitutionChange = useCallback((id: string) => setInstitutionId(id), []);
  const onDataChange = useCallback(() => setOverviewRefresh(v => v + 1), []);
  const searchRecords = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    window.dispatchEvent(new CustomEvent('depositguard:search-record', { detail: search }));
  };

  if (auth.loading) {
    return (
      <main className="auth-page">
        <section className="auth-card" role="status">
          <p>Loading session…</p>
        </section>
      </main>
    );
  }

  // Public routes
  if (location.pathname === '/' ) {
    return auth.session ? <Navigate to="/dashboard" replace /> : <Navigate to="/login" replace />;
  }
  if (location.pathname === '/login') {
    return auth.session ? <Navigate to="/dashboard" replace /> : <SignInScreen />;
  }
  if (location.pathname === '/signup') return <SignUpScreen />;
  if (location.pathname === '/pending-approval') return <PendingApprovalScreen />;
  if (location.pathname === '/admin/approvals') {
    if (!auth.session?.user.system_admin) {
      return (
        <div className="auth-page"><div className="auth-card" role="alert">Access denied</div></div>
      );
    }
    return <AdminUserApprovalScreen />;
  }
  // Protected routes – require authentication
  if (!auth.session) return <SignInScreen />;
  if (auth.session.user.must_change_password) return <PasswordChangeScreen />;

  // Main application UI
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumbs"><span>Workspace</span><span className="crumb-sep">/</span><strong>{title}</strong></div>
          <div className="top-actions">
            <form className="search-box" role="search" onSubmit={searchRecords}>
              <Search size={16} />
              <input aria-label="Search selected institution records" placeholder="Search selected institution…" value={search} onChange={e => setSearch(e.target.value)} />
              <kbd>Enter</kbd>
            </form>
            <Link className="help-button" to="/settings"><CircleHelp size={17} /> Help</Link>
          </div>
        </header>
        <div className="page-wrap">
          {auth.error && <div className="auth-error" role="alert">{auth.error}</div>}
          <section className="welcome-row"><div><h1>{title}</h1><p>{title === 'Dashboard' ? institutionId ? `Summary of persisted data for institution ${institutionId}.` : 'Summary of persisted data in the selected local institution.' : 'Local DepositGuard workspace'}</p></div></section>
          <FdrWorkspace onInstitutionChange={onInstitutionChange} onDataChange={onDataChange} overviewRefresh={overviewRefresh} />
          <footer><span>DepositGuard <span className="footer-sep">·</span> Local prototype</span><span><ArrowDownToLine size={13} /> Local database only · synthetic data only</span></footer>
        </div>
      </main>
    </div>
  );
}

export default App;
