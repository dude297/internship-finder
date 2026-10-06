import type { ApplicationInput, ApplicationStatus } from '../api/schemas'

// ADR-025: the application workspace's stages and quick actions. Stages are a pipeline for
// scanning, not a required sequence: any status may follow any other.

export const pipelineColumns: {
  key: string
  label: string
  statuses: ApplicationStatus[]
}[] = [
  { key: 'saved', label: 'Saved', statuses: ['saved'] },
  { key: 'applying', label: 'Applying', statuses: ['applying'] },
  { key: 'applied', label: 'Applied', statuses: ['applied'] },
  { key: 'interview', label: 'Interview', statuses: ['interview'] },
  { key: 'offer', label: 'Offer', statuses: ['offer'] },
  { key: 'outcome', label: 'Outcome', statuses: ['accepted', 'rejected', 'withdrawn'] },
]

export const finished: ApplicationStatus[] = ['accepted', 'rejected', 'withdrawn']
export const isFinished = (s: ApplicationStatus) => finished.includes(s)

export type QuickAction =
  | 'start'
  | 'applied'
  | 'follow_up'
  | 'interview'
  | 'offer'
  | 'accept'
  | 'reject'
  | 'withdraw'

/** Which actions make sense now. Offered, never enforced: the stage selector reaches anything. */
export function availableActions(status: ApplicationStatus): QuickAction[] {
  switch (status) {
    case 'saved':
      return ['start', 'applied', 'follow_up']
    case 'applying':
      return ['applied', 'follow_up', 'withdraw']
    case 'applied':
      return ['follow_up', 'interview', 'reject', 'withdraw']
    case 'interview':
      return ['follow_up', 'interview', 'offer', 'reject', 'withdraw']
    case 'offer':
      return ['accept', 'reject', 'withdraw']
    default:
      return []
  }
}

export const actionLabels: Record<QuickAction, string> = {
  start: 'Start application',
  applied: 'Mark applied',
  follow_up: 'Schedule follow-up',
  interview: 'Add interview',
  offer: 'Mark offer',
  accept: 'Accept',
  reject: 'Reject',
  withdraw: 'Withdraw',
}

/** The patch a quick action sends (the API merges only what is sent). */
export function patchFor(
  action: QuickAction,
  current: ApplicationStatus,
  detail: {
    followUpDate?: string
    followUpText?: string
    interviewAt?: string
    updatedAt?: string
  } = {},
): ApplicationInput {
  const patch = basePatch(action, current, detail)
  // Guard against a stale screen: the server refuses if the application changed meanwhile.
  return detail.updatedAt ? { ...patch, expected_updated_at: detail.updatedAt } : patch
}

function basePatch(
  action: QuickAction,
  _current: ApplicationStatus,
  detail: { followUpDate?: string; followUpText?: string; interviewAt?: string },
): ApplicationInput {
  switch (action) {
    case 'start':
      return { status: 'applying' }
    case 'applied':
      return { status: 'applied' }
    case 'follow_up':
      // No status: a follow-up must never resend (and so revert) a stale one.
      return {
        next_action: detail.followUpText?.trim() || 'Follow up',
        next_action_due: detail.followUpDate ?? null,
      }
    case 'interview':
      return {
        status: 'interview',
        interview_at: detail.interviewAt
          ? new Date(detail.interviewAt).toISOString()
          : null,
      }
    case 'offer':
      return { status: 'offer' }
    case 'accept':
      return { status: 'accepted' }
    case 'reject':
      return { status: 'rejected' }
    case 'withdraw':
      return { status: 'withdrawn' }
  }
}

export function eventLabel(
  type: string,
  from: ApplicationStatus | null,
  to: ApplicationStatus | null,
  labels: Record<ApplicationStatus, string>,
): string {
  switch (type) {
    case 'created':
      return `Started tracking${to ? ` as ${labels[to]}` : ''}`
    case 'status_changed':
      return `Status: ${from ? labels[from] : '—'} → ${to ? labels[to] : '—'}`
    case 'next_action_changed':
      return 'Next action changed'
    case 'deadline_changed':
      return 'Follow-up date changed'
    case 'interview_scheduled':
      return 'Interview scheduled'
    case 'interview_updated':
      return 'Interview updated'
    case 'note_added':
      return 'Note added'
    case 'offer_received':
      return 'Offer received'
    default:
      return type
  }
}
