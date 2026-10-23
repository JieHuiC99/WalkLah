import { useEffect, useRef, type ReactNode } from 'react'
import { Icon } from '../components/icons'

/** Modal sheet inside the phone (absolute, so it stays within the device frame). */
export function Sheet({
  title,
  kicker,
  onClose,
  children,
  tall = false,
}: {
  title: string
  kicker?: string
  onClose: () => void
  children: ReactNode
  tall?: boolean
}) {
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="go-modal" onClick={onClose}>
      <section
        className={`go-modal__sheet${tall ? ' go-modal__sheet--tall' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="go-modal__head">
          <div>
            {kicker && <span className="stage-tag">{kicker}</span>}
            <h2>{title}</h2>
          </div>
          <button ref={closeRef} type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            <Icon name="x" size={20} />
          </button>
        </header>
        <div className="go-modal__body">{children}</div>
      </section>
    </div>
  )
}
