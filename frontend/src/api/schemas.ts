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
  'volunteer',
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

export const origins = ['imported', 'manual'] as const
export const availabilities = ['open', 'closed', 'manual'] as const
export const sourceKinds = [
  'community_feed',
  'greenhouse',
  'lever',
  'ashby',
  'smartrecruiters',
  'curated_registry',
] as const
export const regions = ['global', 'eu'] as const
export const runStatuses = [
  'running',
  'success',
  'partial',
  'failed',
  'no_change',
] as const
export const sourceScopes = ['internships_only', 'all'] as const
export const sourceHealths = [
  'never_run',
  'healthy',
  'warning',
  'stale',
  'failing',
  'disabled',
] as const
export type SourceHealth = (typeof sourceHealths)[number]
export const remotePreferences = [
  'no_preference',
  'remote_preferred',
  'hybrid_preferred',
  'onsite_preferred',
  'remote_only',
] as const
export type SourceScope = (typeof sourceScopes)[number]
export type RemotePreference = (typeof remotePreferences)[number]
export type Origin = (typeof origins)[number]
export type Availability = (typeof availabilities)[number]
export type SourceKind = (typeof sourceKinds)[number]
export type Region = (typeof regions)[number]
export type RunStatus = (typeof runStatuses)[number]

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
  extractor_name: z.string().nullable(),
  extractor_version: z.string().nullable(),
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

// Fit v1 (ADR-010). The backend computes every score; the UI only displays them.
export const fitComponentKeys = [
  'technical',
  'academic',
  'projects',
  'interests',
  'location_schedule',
  'quality',
] as const
export type FitComponentKey = (typeof fitComponentKeys)[number]

export const fitComponentSchema = z.object({
  score: z.number().int(),
  weight: z.number().int(),
  missing: z.boolean(),
  missing_input: z.enum(['profile', 'opportunity']).nullable(),
  reason: z.string(),
  matched: z.array(z.string()),
  unmatched: z.array(z.string()),
  details: z.record(z.string(), z.unknown()).nullable(),
})
export type FitComponent = z.infer<typeof fitComponentSchema>

export const scoreBreakdownSchema = z.object({
  scoring_version: z.string(),
  score: z.number().int(),
  coverage: z.number().int(),
  components: z.record(z.string(), fitComponentSchema),
})
export type ScoreBreakdown = z.infer<typeof scoreBreakdownSchema>

export const evaluationSchema = z.object({
  id: z.string(),
  eligibility_status: z.enum(eligibilityStatuses),
  eligibility_rules_version: z.string(),
  depends_on_projected_status: z.boolean(),
  evaluated_at: z.string(),
  rule_results: z.array(ruleResultSchema),
  fit_score: z.number().int().nullable(),
  scoring_version: z.string().nullable(),
  score_breakdown: scoreBreakdownSchema.nullable(),
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
  // Date trust (ADR-014 §6): typical windows are hints, never deadlines.
  program_cycle: z.string().nullable().default(null),
  typical_open_window: z.string().nullable().default(null),
  typical_close_window: z.string().nullable().default(null),
  verify_by: nullableDate.default(null),
  needs_date_verification: z.boolean().default(false),
  start_date: nullableDate,
  posted_at: z.string().nullable(),
  first_seen_at: z.string(),
  requirements_assessment_status: z.enum(assessmentStatuses),
  eligibility_status: z.enum(eligibilityStatuses).nullable(),
  evaluated_at: z.string().nullable(),
  fit_score: z.number().int().nullable(),
  scoring_version: z.string().nullable(),
  fit_coverage: z.number().int().nullable(),
  fit_components: z
    .record(
      z.string(),
      z.object({
        score: z.number().int(),
        weight: z.number().int(),
        missing: z.boolean(),
      }),
    )
    .nullable(),
  application_status: z.enum(applicationStatuses).nullable(),
  origin: z.enum(origins),
  availability: z.enum(availabilities),
  source_names: z.array(z.string()),
  pending_requirement_count: z.number().int(),
  requirements_stale: z.boolean(),
})
export type OpportunitySummary = z.infer<typeof opportunitySummarySchema>

export const opportunityPageSchema = z.object({
  items: z.array(opportunitySummarySchema),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
})
export type OpportunityPage = z.infer<typeof opportunityPageSchema>

export const sourceRecordSchema = z.object({
  source_name: z.string(),
  source_type: z.string(),
  automated: z.boolean(),
  is_active: z.boolean(),
  closed_at: z.string().nullable(),
  first_seen_at: z.string(),
  last_seen_at: z.string(),
  source_url: z.string().nullable(),
  source_published_at: z.string().nullable(),
  source_updated_at: z.string().nullable(),
})
export type SourceRecord = z.infer<typeof sourceRecordSchema>

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
  // Date trust (ADR-014 §6): typical windows are hints, never deadlines.
  program_cycle: z.string().nullable().default(null),
  typical_open_window: z.string().nullable().default(null),
  typical_close_window: z.string().nullable().default(null),
  verify_by: nullableDate.default(null),
  needs_date_verification: z.boolean().default(false),
  start_date: nullableDate,
  end_date: nullableDate,
  requirements_assessment_status: z.enum(assessmentStatuses),
  requirements_stale_since: z.string().nullable(),
  pending_requirement_count: z.number().int(),
  created_at: z.string(),
  updated_at: z.string(),
  posted_at: z.string().nullable(),
  first_seen_at: z.string(),
  last_seen_at: z.string(),
  manually_curated_at: z.string().nullable(),
  requirements: z.array(requirementSchema),
  application: applicationSchema.nullable(),
  origin: z.enum(origins),
  availability: z.enum(availabilities),
  sources: z.array(sourceRecordSchema),
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

export const runErrorSchema = z.object({
  external_id: z.string().nullable(),
  stage: z.string(),
  code: z.string(),
  message: z.string(),
})

export const runSchema = z.object({
  id: z.string(),
  source_id: z.string(),
  status: z.enum(runStatuses),
  started_at: z.string(),
  finished_at: z.string().nullable(),
  source_generated_at: z.string().nullable(),
  fetched_count: z.number().int(),
  filtered_count: z.number().int(),
  normalized_count: z.number().int(),
  created_count: z.number().int(),
  updated_count: z.number().int(),
  deduplicated_count: z.number().int(),
  unchanged_count: z.number().int(),
  closed_count: z.number().int(),
  reactivated_count: z.number().int(),
  invalid_count: z.number().int(),
  error_count: z.number().int(),
  error_summary: z.string().nullable(),
  errors: z.array(runErrorSchema),
})
export type Run = z.infer<typeof runSchema>

export const sourceSchema = z.object({
  id: z.string(),
  kind: z.enum(sourceKinds),
  key: z.string(),
  identifier: z.string(),
  region: z.enum(regions).nullable(),
  display_name: z.string(),
  enabled: z.boolean(),
  scope: z.enum(sourceScopes),
  builtin: z.boolean(),
  last_attempted_at: z.string().nullable(),
  last_success_at: z.string().nullable(),
  latest_run: runSchema.nullable(),
  health: z.enum(sourceHealths),
  consecutive_failures: z.number().int(),
  last_success_age_hours: z.number().nullable(),
})
export type Source = z.infer<typeof sourceSchema>

export interface SourceInput {
  kind: SupportedSourceKind
  display_name: string
  board: string
  region: Region | null
  scope: SourceScope
}

export const matchItemSchema = z.object({
  name: z.string(),
  description: z.string().nullable(),
})
export type MatchItem = z.infer<typeof matchItemSchema>

export const matchProfileSchema = z.object({
  skills: z.array(z.string()),
  courses: z.array(z.string()),
  projects: z.array(matchItemSchema),
  research: z.array(matchItemSchema),
  activities: z.array(matchItemSchema),
  experience: z.array(matchItemSchema),
  interests: z.array(z.string()),
  preferred_locations: z.array(z.string()),
  remote_preference: z.enum(remotePreferences).nullable(),
  availability_start: nullableDate,
  availability_end: nullableDate,
})
export type MatchProfile = z.infer<typeof matchProfileSchema>

export const matchProfileSaveSchema = z.object({
  match_profile: matchProfileSchema,
  evaluated_opportunities: z.number().int(),
  unchanged_opportunities: z.number().int(),
})

// Profile sources: imported resume facts awaiting review (ADR-011 §8-9). Imported facts never
// affect matching until accepted; only skill/course/project/research feed the Match Profile.
export const factCategories = [
  'skill',
  'course',
  'project',
  'research',
  'experience',
  'activity',
  'award',
  'education',
] as const
export type FactCategory = (typeof factCategories)[number]

export const reviewStates = ['pending', 'accepted', 'rejected'] as const
export type ReviewState = (typeof reviewStates)[number]

export const importedFactSchema = z.object({
  id: z.string(),
  category: z.enum(factCategories),
  name: z.string(),
  description: z.string().nullable(),
  review_state: z.enum(reviewStates),
})
export type ImportedFact = z.infer<typeof importedFactSchema>

export const profileSourceSummarySchema = z.object({
  id: z.string(),
  kind: z.literal('resume'),
  original_filename: z.string().nullable(),
  content_type: z.string(),
  byte_size: z.number().int(),
  parser_name: z.string(),
  parser_version: z.string(),
  ingested_at: z.string(),
  pending_count: z.number().int(),
  accepted_count: z.number().int(),
  rejected_count: z.number().int(),
})
export type ProfileSourceSummary = z.infer<typeof profileSourceSummarySchema>

export const profileSourceDetailSchema = profileSourceSummarySchema.extend({
  facts: z.array(importedFactSchema),
})
export type ProfileSourceDetail = z.infer<typeof profileSourceDetailSchema>

export const profileSourceReviewResultSchema = z.object({
  source: profileSourceDetailSchema,
  catalog_pass: z.boolean(),
  evaluated_opportunities: z.number().int(),
  unchanged_opportunities: z.number().int(),
})
export type ProfileSourceReviewResult = z.infer<typeof profileSourceReviewResultSchema>

export const profileSourceDeleteResultSchema = z.object({
  catalog_pass: z.boolean(),
  evaluated_opportunities: z.number().int(),
  unchanged_opportunities: z.number().int(),
})
export type ProfileSourceDeleteResult = z.infer<typeof profileSourceDeleteResultSchema>

// Source discovery / coverage (ADR-013 §2, §3): derived on read, never stored.

export const supportedSourceKinds = [
  'greenhouse',
  'lever',
  'ashby',
  'smartrecruiters',
] as const
export type SupportedSourceKind = (typeof supportedSourceKinds)[number]

export const coverageMetricsSchema = z.object({
  active_opportunities: z.number().int(),
  with_description: z.number().int(),
  without_description: z.number().int(),
  description_coverage_percent: z.number().nullable(),
  ats_backed: z.number().int(),
  feed_only: z.number().int(),
  enrichable: z.number().int(),
  unsupported: z.number().int(),
})
export type CoverageMetrics = z.infer<typeof coverageMetricsSchema>

export const providerCountSchema = z.object({
  provider: z.string(),
  supported: z.boolean(),
  opportunities: z.number().int(),
  enrichable: z.number().int(),
})
export type ProviderCount = z.infer<typeof providerCountSchema>

export const sourceSuggestionSchema = z.object({
  kind: z.enum(supportedSourceKinds),
  identifier: z.string(),
  region: z.enum(regions).nullable(),
  key: z.string(),
  suggested_display_name: z.string(),
  display_name_ambiguous: z.boolean(),
  matching_opportunities: z.number().int(),
  feed_only_opportunities: z.number().int(),
  already_configured: z.boolean(),
  sample_titles: z.array(z.string()),
})
export type SourceSuggestion = z.infer<typeof sourceSuggestionSchema>

export const sourceDiscoveryResponseSchema = z.object({
  coverage: coverageMetricsSchema,
  providers: z.array(providerCountSchema),
  suggestions: z.array(sourceSuggestionSchema),
})
export type SourceDiscoveryResponse = z.infer<typeof sourceDiscoveryResponseSchema>

export const discoveryAddSkippedSchema = z.object({
  key: z.string(),
  reason: z.literal('already_configured'),
})

export const discoveryAddResponseSchema = z.object({
  created: z.array(sourceSchema),
  skipped: z.array(discoveryAddSkippedSchema),
})
export type DiscoveryAddResponse = z.infer<typeof discoveryAddResponseSchema>

/** What the server accepts back (ADR-013 §3): identity only, never a display name or URL. */
export interface DiscoverySelectionInput {
  kind: SupportedSourceKind
  identifier: string
  region: Region | null
}

export interface FactReviewInput {
  id: string
  name?: string
  description?: string | null
}

export interface ProfileSourceReviewInput {
  accept: FactReviewInput[]
  reject: string[]
}

/** Server-side list query (GET /api/opportunities). Empty values are omitted. */
export interface OpportunityQuery {
  limit: number
  offset: number
  q?: string
  availability?: 'open' | 'closed' | 'all'
  source?: string
  eligibility?: string
  application_status?: string
  remote_mode?: string
  opportunity_type?: string
  sort?: 'recommended' | 'newest' | 'deadline'
  requirements_assessment_status?: string
  requirement_review?: 'pending' | 'stale' | 'needs_review'
  deadline_within?: '7' | '14' | '30'
  has_deadline?: 'true'
  needs_date_verification?: 'true'
  // The browser's local date (YYYY-MM-DD); sent whenever a deadline filter is used (ADR-012 §14).
  today?: string
}

// Requirement candidate review (ADR-012 §7). Candidates are deterministic extractor proposals;
// they never affect eligibility until accepted into a canonical requirement.

export const requirementCandidateSchema = z.object({
  id: z.string(),
  requirement_type: z.enum(requirementTypes),
  value: z.record(z.string(), z.unknown()),
  applies_at: z.enum(appliesAtValues),
  reference_date: nullableDate,
  source_text: z.string(),
  extractor_name: z.string(),
  extractor_version: z.string(),
  review_state: z.enum(reviewStates),
  is_current: z.boolean(),
  accepted_requirement_id: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type RequirementCandidate = z.infer<typeof requirementCandidateSchema>

export const requirementReviewResponseSchema = z.object({
  opportunity_id: z.string(),
  requirements_assessment_status: z.enum(assessmentStatuses),
  requirements_stale_since: z.string().nullable(),
  manually_curated: z.boolean(),
  candidates: z.array(requirementCandidateSchema),
  requirements: z.array(requirementSchema),
})
export type RequirementReviewResponse = z.infer<typeof requirementReviewResponseSchema>

export const requirementReviewResultSchema = z.object({
  review: requirementReviewResponseSchema,
  evaluated: z.boolean(),
})
export type RequirementReviewResult = z.infer<typeof requirementReviewResultSchema>

export interface CandidateAcceptInput {
  id: string
  value?: Record<string, unknown>
  applies_at?: AppliesAt
  reference_date?: string | null
}

export interface RequirementReviewInput {
  accept: CandidateAcceptInput[]
  reject: string[]
  assessment_status?: AssessmentStatus
}
