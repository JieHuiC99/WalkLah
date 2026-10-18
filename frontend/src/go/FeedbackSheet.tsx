import { useState } from 'react'
import * as api from '../api/walklahApi'
import { Icon } from '../components/icons'
import type { RouteMode } from '../types'
import { deviceId } from './lib'
import { Sheet } from './Sheet'

/** "After your walk" — validation evidence for the proposal's success metrics. */
export function FeedbackSheet({ mode, onClose }: { mode: RouteMode; onClose: () => void }) {
  const [passable, setPassable] = useState<'yes' | 'partly' | 'no' | null>(null)
  const [note, setNote] = useState('')
  const [state, setState] = useState<'idle' | 'sending' | 'sent'>('idle')
  const [error, setError] = useState<string | null>(null)

  const send = async () => {
    if (!passable) return setError('Choose an answer first.')
    setState('sending')
    setError(null)
    try {
      await api.sendFeedback(mode, passable, note.trim() || null, deviceId())
      setState('sent')
    } catch (err) {
      setError(api.errorMessage(err))
      setState('idle')
    }
  }

  return (
    <Sheet title="After your walk" onClose={onClose}>
      {state === 'sent' ? (
        <div className="success-card">
          <Icon name="check" size={22} />
          <div>
            <strong>Thank you!</strong>
            <p>This helps check whether WalkLah's advice matches what walkers find.</p>
          </div>
        </div>
      ) : (
        <>
          <p className="muted">Was the {mode} route passable all the way?</p>
          <div className="segmented segmented--three" role="radiogroup">
            {(['yes', 'partly', 'no'] as const).map((value) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={passable === value}
                className={passable === value ? 'is-active' : ''}
                onClick={() => setPassable(value)}
              >
                {{ yes: 'Yes', partly: 'Partly', no: 'No' }[value]}
              </button>
            ))}
          </div>
          <textarea
            className="go-textarea"
            value={note}
            maxLength={280}
            rows={2}
            placeholder="Anything we should know? (optional)"
            onChange={(e) => setNote(e.target.value)}
          />
          {error && <p className="inline-error">{error}</p>}
          <button type="button" className="btn btn--primary btn--block" onClick={() => void send()} disabled={state === 'sending'}>
            Send
          </button>
        </>
      )}
    </Sheet>
  )
}
