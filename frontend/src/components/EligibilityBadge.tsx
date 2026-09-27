import type { EligibilityStatus } from '../api/schemas'
import { eligibilityLabels } from '../lib/labels'

const styles: Record<EligibilityStatus | 'none', string> = {
  eligible: 'bg-green-100 text-green-800',
  needs_verification: 'bg-amber-100 text-amber-900',
  ineligible: 'bg-red-100 text-red-800',
  none: 'bg-slate-100 text-slate-700',
}

/** needs_verification is always shown as its own state, never folded into eligible. */
export function EligibilityBadge({ status }: { status: EligibilityStatus | null }) {
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-sm font-medium ${styles[status ?? 'none']}`}
    >
      {status ? eligibilityLabels[status] : 'Not evaluated'}
    </span>
  )
}
