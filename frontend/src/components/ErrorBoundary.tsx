import { Component, type ErrorInfo, type ReactNode } from 'react'

interface State {
  error: Error | null
}

/** Last line of defence: an unexpected rendering error shows a message, never a blank screen. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('WalkLah crashed while rendering', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <main className="crash-screen" role="alert">
        <h1>Something went wrong</h1>
        <p>WalkLah hit an unexpected error. Reloading usually fixes it.</p>
        <pre>{this.state.error.message}</pre>
        <button type="button" className="btn btn--primary" onClick={() => window.location.reload()}>
          Reload WalkLah
        </button>
      </main>
    )
  }
}
