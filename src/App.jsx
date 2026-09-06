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
import { VerificationProvider } from './state/verification/VerificationContext.jsx';
import VerificationPage from './pages/VerificationPage.jsx';
import ErrorBoundary from './components/common/ErrorBoundary.jsx';

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary title="System Encountered An Unexpected Error">
        <VerificationProvider>
          <Routes>
            <Route path="/" element={<VerificationPage />} />
            {/* Redirect any unknown path back to root */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </VerificationProvider>
      </ErrorBoundary>
    </BrowserRouter>
  );
}
