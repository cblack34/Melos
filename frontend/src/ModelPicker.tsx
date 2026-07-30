import { useEffect, useState } from 'react'
import type { ModelOptions } from './api'

interface Props {
  generationModel: string
  metaModel: string
  onGenerationModelChange: (id: string) => void
  onMetaModelChange: (id: string) => void
}

type LoadState = 'idle' | 'loading' | 'ready' | 'error'

// Behind a disclosure, not shown by default: this is a "trying different
// models" tool, not something most users need to see every time.
export default function ModelPicker({
  generationModel,
  metaModel,
  onGenerationModelChange,
  onMetaModelChange,
}: Props) {
  const [options, setOptions] = useState<ModelOptions | null>(null)
  const [status, setStatus] = useState<LoadState>('idle')
  const [open, setOpen] = useState(false)
  // Bumped to re-run the fetch after an error without treating failure as
  // "still loading" forever (status alone would either loop or stick).
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!open || status === 'ready') return
    let cancelled = false
    setStatus('loading')
    fetch('/api/models')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json() as Promise<ModelOptions>
      })
      .then((data) => {
        if (cancelled) return
        setOptions(data)
        setStatus('ready')
      })
      .catch(() => {
        if (cancelled) return
        setOptions(null)
        setStatus('error')
      })
    return () => {
      cancelled = true
    }
    // `status` is intentionally not a dependency: including it would re-fire
    // on every loading→error transition. `attempt` is the explicit retry
    // signal; reopening after a failed fetch also re-runs via `open`.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- see above
  }, [open, attempt])

  return (
    <div className="model-picker">
      <button
        type="button"
        className="ghost"
        aria-expanded={open}
        aria-controls="model-picker-body"
        onClick={() => setOpen((wasOpen) => !wasOpen)}
      >
        ⚙ Model
      </button>
      <div id="model-picker-body" className="model-picker-body" hidden={!open}>
        {status === 'loading' || status === 'idle' ? (
          <p className="hint">Loading models…</p>
        ) : status === 'error' ? (
          <p className="hint">
            Could not load models.{' '}
            <button
              type="button"
              className="ghost"
              onClick={() => {
                setStatus('idle')
                setAttempt((n) => n + 1)
              }}
            >
              Retry
            </button>
          </p>
        ) : (
          <>
            <label>
              Generation model
              <select
                value={generationModel}
                onChange={(e) => onGenerationModelChange(e.target.value)}
              >
                <option value="">server default</option>
                {(options?.generation ?? []).map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Meta model
              <select
                value={metaModel}
                onChange={(e) => onMetaModelChange(e.target.value)}
              >
                <option value="">server default</option>
                {(options?.meta ?? []).map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.label}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
      </div>
    </div>
  )
}
