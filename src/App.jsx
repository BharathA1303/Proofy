/**
 * App.jsx
 *
 * Root application component.
 * Wraps the application with VerificationProvider (single source of truth)
 * and sets up React Router for future page expansion.
 *
 * Current routes:
 *   /   → VerificationPage (the main verification workspace)
 *
 * Phase 1+ routes to add:
 *   /audit      → Audit log viewer
 *   /settings   → System configuration
 */
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './state/auth/AuthContext.jsx';
import { useAuth } from './state/auth/useAuth.js';
import { VerificationProvider } from './state/verification/VerificationContext.jsx';
import VerificationPage from './pages/VerificationPage.jsx';
import LoginPage from './pages/auth/LoginPage.jsx';
import RegisterPage from './pages/auth/RegisterPage.jsx';
import ErrorBoundary from './components/common/ErrorBoundary.jsx';

function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary title="System Encountered An Unexpected Error">
        <AuthProvider>
          <VerificationProvider>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route
                path="/"
                element={
                  <ProtectedRoute>
                    <VerificationPage />
                  </ProtectedRoute>
                }
              />
              {/* Redirect any unknown path back to root */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </VerificationProvider>
        </AuthProvider>
      </ErrorBoundary>
    </BrowserRouter>
  );
}
