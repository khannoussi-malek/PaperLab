import { Component, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'

type Props = { onRetry: () => void; children: ReactNode }

/** Catches a page that fails to load or to render (a lazy chunk that didn't arrive) so the window doesn't go blank. */
export class RouteErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div role="alert" className="flex flex-col items-start gap-3 p-6 text-sm">
        <p>This page couldn&apos;t load. Check your connection and try again.</p>
        <Button onClick={this.props.onRetry}>Try again</Button>
      </div>
    )
  }
}
