import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = { children: ReactNode }

type State = { error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('UI error:', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="error-boundary">
          <h1 className="error-boundary__title">Something broke in the UI</h1>
          <pre className="error-boundary__msg">{this.state.error.message}</pre>
          <p className="error-boundary__hint">
            Open the browser console for the full stack. Try a hard refresh (Cmd+Shift+R). If you
            changed the API, restart the backend so it matches the frontend.
          </p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => this.setState({ error: null })}
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
