import { ArrowLeft } from 'lucide-react'
import { fadeIn } from '@/components/motion'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { ModelsSettings } from './ModelsSettings'

/** `#/settings`: model connections (which models chat lists, and the default) and the embedding model. */
export function SettingsPage() {
  return (
    <main className={cn('mx-auto flex max-w-3xl flex-col gap-8 px-4 py-6', fadeIn)}>
      <div>
        <Button variant="ghost" size="sm" asChild className="-ml-2.5">
          <a href="#/">
            <ArrowLeft aria-hidden />
            Library
          </a>
        </Button>
        <h1 className="mt-1 font-heading text-3xl font-semibold">Settings</h1>
      </div>

      <ModelsSettings />
    </main>
  )
}
