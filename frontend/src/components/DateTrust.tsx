import { formatDate } from '../lib/labels'

// Date trust (ADR-014 §6): only a verified application_deadline is ever shown as a deadline.
// A typical window is a muted hint that is explicitly not confirmed.

export function DeadlineText({ deadline }: { deadline: string | null }) {
  return <>{deadline ? formatDate(deadline) : 'No confirmed deadline'}</>
}

export function NeedsDateBadge({ verifyBy }: { verifyBy: string | null }) {
  return (
    <span
      className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900"
      title={verifyBy ? `Verify by ${formatDate(verifyBy)}` : undefined}
    >
      Needs date verification
      {verifyBy && ` (verify by ${formatDate(verifyBy)})`}
    </span>
  )
}

interface Windows {
  program_cycle: string | null
  typical_open_window: string | null
  typical_close_window: string | null
}

export function TypicalWindow({ o }: { o: Windows }) {
  if (!o.typical_open_window && !o.typical_close_window) return null
  const parts = [
    o.typical_open_window && `opens ${o.typical_open_window}`,
    o.typical_close_window && `closes ${o.typical_close_window}`,
  ].filter(Boolean)
  return (
    <p className="mt-1 text-xs text-slate-500">
      Typical application window: {parts.join(' · ')} (not confirmed
      {o.program_cycle ? ` for ${o.program_cycle}` : ''})
    </p>
  )
}
