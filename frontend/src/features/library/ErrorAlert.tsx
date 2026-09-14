import { glass } from '@/components/glass'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** The destructive alert every load or mutation failure shows, styled once. Shared by the library and workspaces. */
export function ErrorAlert({ message }: { message: string }) {
  return (
    <Alert variant="destructive" className={cn('border-glass-border', glass)}>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  )
}

/** A failed list load: the error, and a way to try again. Shared by the library and a workspace's Papers tab. */
export function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <>
      <ErrorAlert message={message} />
      <Button variant="outline" className="self-start" onClick={onRetry}>
        Retry
      </Button>
    </>
  )
}
