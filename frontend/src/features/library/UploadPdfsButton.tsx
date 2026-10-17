import { Upload } from 'lucide-react'
import { useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Hint } from '@/components/Hint'

type Props = {
  onUpload: (files: File[]) => void
  isPending: boolean
  /** "Upload PDFs" is the primary action in the library, but an outline one beside a workspace's "Add from library". */
  variant?: 'default' | 'outline'
  /** Tooltip on the button. */
  hint?: string
}

/** The "Upload PDFs" button and its hidden file input. Shared by the library and a workspace's Papers tab. */
export function UploadPdfsButton({ onUpload, isPending, variant, hint }: Props) {
  const fileInput = useRef<HTMLInputElement>(null)

  function onFiles(input: HTMLInputElement) {
    const files = [...(input.files ?? [])]
    input.value = ''
    if (files.length > 0) onUpload(files)
  }

  return (
    <>
      <Hint hint={hint}>
        <Button type="button" variant={variant} disabled={isPending} onClick={() => fileInput.current?.click()}>
          <Upload aria-hidden />
          {isPending ? 'Uploading…' : 'Upload PDFs'}
        </Button>
      </Hint>
      <input
        ref={fileInput}
        type="file"
        accept="application/pdf"
        multiple
        hidden
        onChange={(e) => onFiles(e.currentTarget)}
      />
    </>
  )
}
