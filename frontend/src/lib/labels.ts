import type {
  AppliesAt,
  ApplicationStatus,
  AssessmentStatus,
  EducationLevel,
  EligibilityStatus,
  OpportunityType,
  RemoteMode,
  RequirementType,
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
