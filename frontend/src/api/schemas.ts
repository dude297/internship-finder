import { z } from 'zod'

// Mirrors the backend response models (app/schemas). Backend validation is authoritative;
// these only make sure the UI never renders a shape it doesn't understand.

export const educationLevels = ['high_school', 'undergraduate', 'graduate'] as const
export const opportunityTypes = [
  'internship',
  'research',
  'fellowship',
  'summer_program',
  'scholarship',
  'competition',
  'other',
] as const
export const remoteModes = ['onsite', 'remote', 'hybrid'] as const
export const assessmentStatuses = ['unassessed', 'partial', 'complete'] as const
export const eligibilityStatuses = [
  'eligible',
  'needs_verification',
  'ineligible',
] as const
export const requirementTypes = [
  'minimum_age',
  'education',
  'citizenship',
  'work_authorization',
  'other',
] as const
export const appliesAtValues = ['program_start', 'application', 'explicit_date'] as const
export const applicationStatuses = [
  'saved',
  'applying',
  'applied',
  'interview',
  'offer',
  'accepted',
  'rejected',
  'withdrawn',
] as const

export type EducationLevel = (typeof educationLevels)[number]
export type OpportunityType = (typeof opportunityTypes)[number]
export type RemoteMode = (typeof remoteModes)[number]
export type AssessmentStatus = (typeof assessmentStatuses)[number]
export type EligibilityStatus = (typeof eligibilityStatuses)[number]
export type RequirementType = (typeof requirementTypes)[number]
export type AppliesAt = (typeof appliesAtValues)[number]
export type ApplicationStatus = (typeof applicationStatuses)[number]

const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/)
const nullableDate = isoDate.nullable()

export const sessionSchema = z.object({
  authenticated: z.boolean(),
  username: z.string().nullable(),
  csrf_token: z.string().nullable(),
})
export type SessionInfo = z.infer<typeof sessionSchema>

export const profileSchema = z.object({
  id: z.string(),
  updated_at: z.string(),
  current_education_level: z.enum(educationLevels).nullable(),
  current_grade: z.string().nullable(),
  education_status_as_of: nullableDate,
  expected_graduation_date: nullableDate,
  expected_enrollment_date: nullableDate,
  expected_future_education_level: z.enum(educationLevels).nullable(),
  date_of_birth: nullableDate,
  citizenships: z.array(z.string()).nullable(),
  work_authorizations: z.array(z.string()).nullable(),
  location: z.string().nullable(),
})
export type Profile = z.infer<typeof profileSchema>
export type ProfileInput = Omit<Profile, 'id' | 'updated_at'>

export const profileSaveSchema = z.object({
  profile: profileSchema,
  reevaluated_opportunities: z.number().int(),
})

export const applicationSchema = z.object({
  status: z.enum(applicationStatuses),
  submitted_on: nullableDate,
  notes: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type Application = z.infer<typeof applicationSchema>
export type ApplicationInput = Pick<Application, 'status' | 'submitted_on' | 'notes'>

export const requirementSchema = z.object({
  id: z.string(),
  requirement_type: z.enum(requirementTypes),
  value: z.record(z.string(), z.unknown()),
  applies_at: z.enum(appliesAtValues),
  reference_date: nullableDate,
  source_text: z.string().nullable(),
  extraction_method: z.string(),
})
export type Requirement = z.infer<typeof requirementSchema>

export const ruleResultSchema = z.object({
  rule_id: z.string(),
  requirement_id: z.string().nullable(),
  status: z.enum(eligibilityStatuses),
  reason: z.string(),
  reference_date: nullableDate,
  depends_on_projected_status: z.boolean(),
  details: z.record(z.string(), z.unknown()).nullable(),
})
export type RuleResult = z.infer<typeof ruleResultSchema>

export const evaluationSchema = z.object({
  id: z.string(),
  eligibility_status: z.enum(eligibilityStatuses),
  eligibility_rules_version: z.string(),
  depends_on_projected_status: z.boolean(),
  evaluated_at: z.string(),
  rule_results: z.array(ruleResultSchema),
})
export type Evaluation = z.infer<typeof evaluationSchema>

export const opportunitySummarySchema = z.object({
  id: z.string(),
  title: z.string(),
  organization: z.string(),
  opportunity_type: z.enum(opportunityTypes),
  location: z.string().nullable(),
  remote_mode: z.enum(remoteModes).nullable(),
  application_deadline: nullableDate,
  start_date: nullableDate,
  requirements_assessment_status: z.enum(assessmentStatuses),
  eligibility_status: z.enum(eligibilityStatuses).nullable(),
  evaluated_at: z.string().nullable(),
  application_status: z.enum(applicationStatuses).nullable(),
})
export type OpportunitySummary = z.infer<typeof opportunitySummarySchema>

export const opportunityDetailSchema = z.object({
  id: z.string(),
  title: z.string(),
  organization: z.string(),
  description: z.string().nullable(),
  opportunity_type: z.enum(opportunityTypes),
  application_url: z.string().nullable(),
  location: z.string().nullable(),
  remote_mode: z.enum(remoteModes).nullable(),
  application_deadline: nullableDate,
  start_date: nullableDate,
  end_date: nullableDate,
  requirements_assessment_status: z.enum(assessmentStatuses),
  created_at: z.string(),
  updated_at: z.string(),
  requirements: z.array(requirementSchema),
  application: applicationSchema.nullable(),
  latest_evaluation: evaluationSchema.nullable(),
  profile_exists: z.boolean(),
})
export type OpportunityDetail = z.infer<typeof opportunityDetailSchema>

export interface RequirementInput {
  requirement_type: RequirementType
  value: Record<string, unknown>
  applies_at: AppliesAt
  reference_date: string | null
  source_text: string | null
}

export interface OpportunityInput {
  title: string
  organization: string
  description: string | null
  opportunity_type: OpportunityType
  application_url: string | null
  location: string | null
  remote_mode: RemoteMode | null
  application_deadline: string | null
  start_date: string | null
  end_date: string | null
  requirements_assessment_status: AssessmentStatus
  requirements: RequirementInput[]
}
