import { Navigate } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';

interface Props {
  children: React.ReactNode;
  requireAdmin?: boolean;
  requireUser?: boolean;
}

export default function ProtectedRoute({ children, requireAdmin = false, requireUser = false }: Props) {
  const { isAuthenticated, isAdmin } = useAuthStore();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (requireAdmin && !isAdmin) {
    return <Navigate to="/" replace />;
  }

  if (requireUser && isAdmin) {
    return <Navigate to="/users" replace />;
  }

  return <>{children}</>;
}
