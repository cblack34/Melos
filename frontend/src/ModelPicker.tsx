import { useEffect, useState } from 'react'
import type { ModelOptions } from './api'

interface Props {
  generationModel: string
  metaModel: string
  onGenerationModelChange: (id: string) => void
  onMetaModelChange: (id: string) => void
}

// Behind a disclosure, not shown by default: this is a "trying different
// models" tool, not something most users need to see every time.
export default function ModelPicker({
  generationModel,
  metaModel,
  onGenerationModelChange,
  onMetaModelChange,
}: Props) {
  const [options, setOptions] = useState<ModelOptions | null>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open || options) return
    let cancelled = false
    fetch('/api/models')
      .then((response) => (response.ok ? response.json() : null))
      .then((data: ModelOptions | null) => {
        if (!cancelled && data) setOptions(data)
      })
      .catch(() => {
        /* leave options null; the picker just stays empty */
      })
    return () => {
      cancelled = true
    }
  }, [open, options])

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
        {options === null ? (
          <p className="hint">Loading models…</p>
        ) : (
          <>
            <label>
              Generation model
              <select
                value={generationModel}
                onChange={(e) => onGenerationModelChange(e.target.value)}
              >
                <option value="">server default</option>
                {options.generation.map((model) => (
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
                {options.meta.map((model) => (
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
