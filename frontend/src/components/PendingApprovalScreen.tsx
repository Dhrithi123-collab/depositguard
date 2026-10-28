import { Link } from 'react-router-dom';
import { ShieldCheck } from 'lucide-react';

export function PendingApprovalScreen() {
  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="auth-brand"><span><ShieldCheck size={22} /></span><div><strong>DepositGuard</strong><small>ACCOUNT PENDING</small></div></div>
        <h1>Registration received</h1>
        <p>Your account has been created and is pending administrator approval. You will receive an email once your account is activated.</p>
        <p className="auth-footnote"><Link to="/login">Back to sign in</Link></p>
      </section>
    </main>
  );
}
