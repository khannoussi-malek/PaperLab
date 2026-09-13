import { useCallback, useEffect, useState } from 'react'
import { api, type Paper } from '../../api/client'
import { readerHref } from '../../lib/route'
import './library.css'

const POLL_MS = 2000
const isSettled = (paper: Paper) => paper.status === 'ready' || paper.status === 'failed'

export function LibraryPage() {
  const [papers, setPapers] = useState<Paper[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  const refresh = useCallback(
    () => api.listPapers().then(setPapers, (e: Error) => setError(e.message)),
    [],
  )

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Poll only while something is still ingesting.
  const ingesting = papers?.some((paper) => !isSettled(paper)) ?? false
  useEffect(() => {
    if (!ingesting) return
    const timer = setInterval(refresh, POLL_MS)
    return () => clearInterval(timer)
  }, [ingesting, refresh])

  async function upload(input: HTMLInputElement) {
    const files = [...(input.files ?? [])]
    input.value = ''
    if (files.length === 0) return
    setUploading(true)
    setError(null)
    try {
      for (const file of files) await api.uploadPaper(file)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setUploading(false)
      await refresh()
    }
  }

  async function remove(paper: Paper) {
    if (!window.confirm(`Delete "${paper.title}"? Its highlights go with it; notes are kept.`)) return
    try {
      await api.deletePaper(paper.id)
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <main className="library">
      <header className="library-header">
        <h1>PaperLab</h1>
        <label className="button button-primary">
          {uploading ? 'Uploading…' : 'Upload PDFs'}
          <input
            type="file"
            accept="application/pdf"
            multiple
            hidden
            disabled={uploading}
            onChange={(e) => void upload(e.currentTarget)}
          />
        </label>
      </header>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {papers === null ? (
        <p>Loading…</p>
      ) : papers.length === 0 ? (
        <p>No papers yet. Upload a PDF to start.</p>
      ) : (
        <ul className="paper-list">
          {papers.map((paper) => (
            <li key={paper.id} className="paper-row">
              <a href={readerHref(paper.id)}>{paper.title}</a>
              <span className={`status status-${paper.status}`}>{paper.status}</span>
              <button type="button" className="link-button" onClick={() => void remove(paper)}>
                Delete
              </button>
              {paper.status_error && <small className="error">{paper.status_error}</small>}
            </li>
          ))}
        </ul>
      )}
    </main>
  )
}
