/**
 * ErrorBoundary.jsx
 *
 * Catch JavaScript errors anywhere in child component tree,
 * log the error, and display a fallback UI instead of crashing the whole page.
 */
import React from 'react';
import styles from './ErrorBoundary.module.css';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an unhandled error:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    if (this.props.onReset) {
      this.props.onReset();
    } else {
      window.location.reload();
    }
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className={styles.errorContainer} role="alert">
          <div className={styles.errorCard}>
            <div className={styles.iconContainer} aria-hidden="true">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>
            <h2 className={styles.title}>{this.props.title || 'Workspace Error Encountered'}</h2>
            <p className={styles.message}>
              {this.state.error?.message || 'An unexpected rendering error occurred in this view.'}
            </p>
            <div className={styles.buttonGroup}>
              <button type="button" className={styles.resetButton} onClick={this.handleReset}>
                Reload Workspace
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
