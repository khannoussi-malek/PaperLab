import { Upload } from 'lucide-react'
import { useRef } from 'react'
import { Button } from '@/components/ui/button'

type Props = {
  onUpload: (files: File[]) => void
  isPending: boolean
  /** "Upload PDFs" is the primary action in the library, but an outline one beside a workspace's "Add papers". */
  variant?: 'default' | 'outline'
}

/** The "Upload PDFs" button and its hidden file input. Shared by the library and a workspace's Papers tab. */
export function UploadPdfsButton({ onUpload, isPending, variant }: Props) {
  const fileInput = useRef<HTMLInputElement>(null)

  function onFiles(input: HTMLInputElement) {
    const files = [...(input.files ?? [])]
    input.value = ''
    if (files.length > 0) onUpload(files)
  }

  return (
    <>
      <Button type="button" variant={variant} disabled={isPending} onClick={() => fileInput.current?.click()}>
        <Upload aria-hidden />
        {isPending ? 'Uploading…' : 'Upload PDFs'}
      </Button>
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
