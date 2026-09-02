import { Component } from 'react'

class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error, info) {
    console.error('ErrorBoundary caught an error:', error, info)
  }

  handleReload = () => {
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="container">
          <section className="card error-boundary">
            <h2>Something went wrong.</h2>
            <p>The app hit an unexpected error. You can try reloading the page.</p>
            <button type="button" onClick={this.handleReload}>
              Reload page
            </button>
          </section>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
