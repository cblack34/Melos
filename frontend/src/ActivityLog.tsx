import type { ProgressEvent } from './api'

export interface LogEntry {
  id: number
  event: ProgressEvent
  at: number // ms since run start
}

interface Props {
  entries: LogEntry[]
  elapsedMs: number | null
  running: boolean
}

const PHASE_LABEL: Record<string, string> = {
  request_received: 'Request received',
  meta_started: 'Resolving meta',
  meta_skipped: 'Meta (supplied)',
  meta_completed: 'Meta ready',
  generation_started: 'Composing',
  model_response: 'Model response',
  validation_retry: 'Retry',
  generation_completed: 'Arrangement OK',
  export_started: 'Building MIDI',
  export_completed: 'MIDI built',
  completed: 'Done',
  failed: 'Failed',
}

function formatElapsed(ms: number): string {
  const totalSec = Math.floor(ms / 1000)
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  return m > 0 ? `${m}:${s.toString().padStart(2, '0')}` : `0:${s.toString().padStart(2, '0')}`
}

function labelFor(event: ProgressEvent): string {
  if (event.phase === 'validation_retry' && event.attempt != null) {
    const max = event.max_attempts != null ? `/${event.max_attempts}` : ''
    return `Retry ${event.attempt}${max}`
  }
  return PHASE_LABEL[event.phase] ?? event.phase
}

export default function ActivityLog({ entries, elapsedMs, running }: Props) {
  return (
    <aside className="activity-log" aria-live="polite" aria-label="Generation activity">
      <header className="activity-log-header">
        <h2>Activity</h2>
        {elapsedMs != null && (
          <span className="activity-elapsed" title="Elapsed time">
            {running ? '● ' : ''}
            {formatElapsed(elapsedMs)}
          </span>
        )}
      </header>
      {entries.length === 0 ? (
        <p className="activity-empty">
          {running ? 'Starting…' : 'Generate a song to see live progress here.'}
        </p>
      ) : (
        <ol className="activity-list">
          {entries.map((entry) => {
            const reasons = entry.event.reasons ?? []
            const expandable = reasons.length > 0
            return (
              <li
                key={entry.id}
                className={`activity-item phase-${entry.event.phase}`}
              >
                <div className="activity-row">
                  <span className="activity-phase">{labelFor(entry.event)}</span>
                  <span className="activity-time">{formatElapsed(entry.at)}</span>
                </div>
                {entry.event.message && (
                  <p className="activity-message">{entry.event.message}</p>
                )}
                {entry.event.provider_response_id && (
                  <p className="activity-generation-id">
                    <span>Provider response ID</span>
                    <code>{entry.event.provider_response_id}</code>
                  </p>
                )}
                {expandable && (
                  <details className="activity-reasons">
                    <summary>
                      {reasons.length} reason{reasons.length === 1 ? '' : 's'}
                    </summary>
                    <ul>
                      {reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </details>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </aside>
  )
}
