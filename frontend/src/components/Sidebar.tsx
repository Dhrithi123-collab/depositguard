import { Activity, Archive, ClipboardCheck, FileSearch, LayoutDashboard, Settings, ShieldCheck, Building2, GitBranch, LogOut } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { useAuth } from './Auth'

const items = [
  { label: 'Dashboard', icon: LayoutDashboard, to: '/dashboard' },
  { label: 'Institutions', icon: Building2, to: '/institutions' },
  { label: 'FDR records', icon: Archive, to: '/fdr-records' },
  { label: 'Documents', icon: FileSearch, to: '/documents' },
  { label: 'Relationships', icon: GitBranch, to: '/relationships' },
  { label: 'Review queue', icon: ClipboardCheck, to: '/review-queue' },
  { label: 'Audit trail', icon: Activity, to: '/audit-trail' },
  { label: 'Settings', icon: Settings, to: '/settings' },
]

export function Sidebar() {
  const { session, logout } = useAuth()
  const user = session!.user
  const role = user.system_admin ? 'System administrator' : user.memberships.length === 1 ? user.memberships[0].role.replace(/_/g, ' ') : 'Institution member'
  return <aside className="sidebar">
    <div className="brand"><div className="brand-mark"><ShieldCheck size={21} strokeWidth={2.3} /></div><div><strong>DepositGuard</strong><span>ASSURANCE WORKSPACE</span></div></div>
    <div className="workspace-label">WORKSPACE</div>
    <nav aria-label="Main navigation" className="nav-list">
      {items.map(({ label, icon: Icon, to }) => <NavLink key={to} to={to} aria-label={label} title={label} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} end>
        <Icon size={18} /><span>{label}</span>
      </NavLink>)}
    </nav>
    <div className="sidebar-bottom">
      <div className="demo-note"><span className="demo-dot" />Synthetic demo workspace</div>
      <div className="profile"><div className="avatar avatar-profile" aria-hidden="true">{user.display_name.slice(0, 1).toUpperCase()}</div><div><strong>{user.display_name}</strong><span>{role}</span></div><button aria-label="Sign out" title="Sign out of DepositGuard" onClick={() => void logout().catch(() => undefined)}><LogOut size={17} /></button></div>
    </div>
  </aside>
}
