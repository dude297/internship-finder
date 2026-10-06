import type {
  AppliesAt,
  ApplicationStatus,
  AssessmentStatus,
  Availability,
  EducationLevel,
  EligibilityStatus,
  FitComponentKey,
  OpportunityType,
  RemoteMode,
  RemotePreference,
  RequirementType,
  RunStatus,
  SourceHealth,
  SourceKind,
  SourceScope,
} from '../api/schemas'

export const educationLevelLabels: Record<EducationLevel, string> = {
  high_school: 'High school',
  undergraduate: 'Undergraduate (college)',
  graduate: 'Graduate school',
}

export const opportunityTypeLabels: Record<OpportunityType, string> = {
  internship: 'Internship',
  research: 'Research',
  fellowship: 'Fellowship',
  summer_program: 'Summer program',
  scholarship: 'Scholarship',
  competition: 'Competition',
  volunteer: 'Volunteer',
  other: 'Other',
}

export const remoteModeLabels: Record<RemoteMode, string> = {
  onsite: 'On-site',
  remote: 'Remote',
  hybrid: 'Hybrid',
}

export const assessmentLabels: Record<AssessmentStatus, string> = {
  unassessed: 'Unassessed',
  partial: 'Some requirements recorded',
  complete: 'All hard requirements reviewed',
}

export const assessmentDescriptions: Record<AssessmentStatus, string> = {
  unassessed: "You haven't reviewed this posting's requirements yet.",
  partial: 'Some requirements are recorded, but others may exist.',
  complete: 'Every hard requirement in the posting is recorded below.',
}

export const eligibilityLabels: Record<EligibilityStatus, string> = {
  eligible: 'Eligible',
  needs_verification: 'Needs verification',
  ineligible: 'Ineligible',
}

export const requirementTypeLabels: Record<RequirementType, string> = {
  minimum_age: 'Minimum age',
  education: 'Education',
  citizenship: 'Citizenship',
  work_authorization: 'Work authorization',
  other: 'Other requirement',
}

export const appliesAtLabels: Record<AppliesAt, string> = {
  program_start: 'On the program start date',
  application: 'On the application deadline',
  explicit_date: 'On a specific date',
}

export const applicationStatusLabels: Record<ApplicationStatus, string> = {
  saved: 'Saved',
  applying: 'Applying',
  applied: 'Applied',
  interview: 'Interview',
  offer: 'Offer',
  accepted: 'Accepted',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
}

export const availabilityLabels: Record<Availability, string> = {
  open: 'Open',
  closed: 'Closed',
  manual: 'Added by hand',
}

export const sourceKindLabels: Record<SourceKind, string> = {
  community_feed: 'Discovery feed (built in)',
  greenhouse: 'Greenhouse',
  lever: 'Lever',
  ashby: 'Ashby',
  smartrecruiters: 'SmartRecruiters',
  curated_registry: 'Curated program registry',
  workable: 'Workable',
  pinpoint: 'Pinpoint',
}

export const sourceHealthLabels: Record<SourceHealth, string> = {
  never_run: 'Never run',
  healthy: 'Healthy',
  warning: 'Warning',
  stale: 'Stale',
  failing: 'Failing',
  disabled: 'Disabled',
}

export const sourceScopeLabels: Record<SourceScope, string> = {
  internships_only: 'Internships only',
  all: 'All postings',
}

export const remotePreferenceLabels: Record<RemotePreference, string> = {
  no_preference: 'No preference',
  remote_preferred: 'Prefer remote',
  hybrid_preferred: 'Prefer hybrid',
  onsite_preferred: 'Prefer on-site',
  remote_only: 'Remote only',
}

export const fitComponentLabels: Record<FitComponentKey, string> = {
  technical: 'Technical skills',
  academic: 'Coursework',
  projects: 'Projects and research',
  interests: 'Interests',
  location_schedule: 'Location and schedule',
  quality: 'Posting quality',
}

export const runStatusLabels: Record<RunStatus, string> = {
  running: 'Running',
  success: 'Succeeded',
  partial: 'Partly succeeded',
  failed: 'Failed',
  no_change: 'No changes',
}

/** The calendar day of a timestamp, in UTC (source dates are usually date-only). */
export function formatDay(iso: string | null): string {
  return formatDate(iso ? iso.slice(0, 10) : null)
}

/** Calendar date (YYYY-MM-DD) for display, without timezone shifts. */
export function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, {
    timeZone: 'UTC',
    dateStyle: 'medium',
  })
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

const DAY_MS = 86_400_000
const utcDay = (iso: string) => Date.parse(`${iso}T00:00:00Z`)

/** "Fri, Oct 9" (year added when it differs from `today`'s), no timezone shift. */
export function formatShortDay(iso: string, today: string): string {
  return new Date(utcDay(iso)).toLocaleDateString('en-US', {
    timeZone: 'UTC',
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    ...(iso.slice(0, 4) !== today.slice(0, 4) && { year: 'numeric' }),
  })
}

/** "Fri, Oct 9 · in 3 days" relative to `today` (both YYYY-MM-DD). */
export function formatDayRelative(iso: string, today: string): string {
  const n = Math.round((utcDay(iso) - utcDay(today)) / DAY_MS)
  const rel =
    n === 0
      ? 'today'
      : n === 1
        ? 'tomorrow'
        : n === -1
          ? 'yesterday'
          : n > 0
            ? `in ${n} days`
            : `${-n} days ago`
  return `${formatShortDay(iso, today)} · ${rel}`
}

/** Rewrites embedded YYYY-MM-DD dates in a sentence to "Fri, Oct 9". */
export function humanizeDates(text: string, today: string): string {
  return text.replace(/\b\d{4}-\d{2}-\d{2}\b/g, (d) => formatShortDay(d, today))
}

export const inboxKindLabels: Record<string, string> = {
  follow_up_overdue: 'Follow-up overdue',
  follow_up_due: 'Follow-up due',
  interview: 'Interview',
  stale: 'Stalled',
}
