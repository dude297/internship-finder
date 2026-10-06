import type { Requirement, RuleResult } from '../api/schemas'
import { educationLevelLabels, formatDate, requirementTypeLabels } from './labels'

// Plain-language wording for stored rule results. This only rephrases what the backend already
// decided (status and details); it never re-evaluates eligibility.

export function ruleTitle(result: RuleResult, requirement?: Requirement): string {
  switch (result.rule_id) {
    case 'ELIG-REQ-000':
      return 'Requirement review'
    case 'ELIG-AGE-001':
      return 'Age'
    case 'ELIG-EDU-001':
      return 'Education'
    case 'ELIG-CIT-001':
      return 'Citizenship'
    case 'ELIG-WA-001':
      return 'Work authorization'
    case 'ELIG-WA-002':
      return 'Sponsorship'
    case 'ELIG-WA-003':
      return 'Citizenship or permanent residency'
    case 'ELIG-WA-004':
      return 'U.S. person (export control)'
    case 'ELIG-WA-005':
      return 'Security clearance'
    default:
      return requirement
        ? requirementTypeLabels[requirement.requirement_type]
        : 'Requirement'
  }
}

const str = (value: unknown) => (typeof value === 'string' ? value : null)
const num = (value: unknown) => (typeof value === 'number' ? value : null)

function levelLabel(level: string | null) {
  return level && level in educationLevelLabels
    ? educationLevelLabels[level as keyof typeof educationLevelLabels].toLowerCase()
    : 'unknown'
}

export function ruleSummary(result: RuleResult): string {
  const details = result.details ?? {}
  const on = result.reference_date ? formatDate(result.reference_date) : null
  switch (result.rule_id) {
    case 'ELIG-REQ-000': {
      const assessment = str(details.requirements_assessment_status)
      if (assessment === 'complete') return 'All hard requirements have been reviewed.'
      if (assessment === 'partial')
        return 'Only some requirements are recorded; others may apply.'
      return "The posting's requirements haven't been reviewed yet, so eligibility can't be confirmed."
    }
    case 'ELIG-AGE-001': {
      const age = num(details.age)
      const minimum = num(details.minimum_age)
      if (!on) return "The date this applies on isn't known yet."
      if (age === null) return 'Add your date of birth to your profile to check this.'
      return result.status === 'eligible'
        ? `You'll be ${age} on ${on}, meeting the minimum age of ${minimum}.`
        : `You'll be ${age} on ${on}, below the minimum age of ${minimum}.`
    }
    case 'ELIG-EDU-001': {
      if (!on) return "The date this applies on isn't known yet."
      const phase = str(details.phase)
      if (result.status === 'needs_verification' || phase === 'unknown')
        return `Your education status on ${on} can't be determined from your profile.`
      const basis = result.depends_on_projected_status ? 'projected' : 'current'
      const status = `${phase === 'incoming' ? 'incoming ' : ''}${levelLabel(str(details.level))}`
      return `Based on your ${basis} status on ${on}: ${status}.`
    }
    case 'ELIG-CIT-001': {
      if (result.status === 'needs_verification')
        return "Citizenship hasn't been entered in your profile."
      const required = Array.isArray(details.required) ? details.required.join(', ') : ''
      return result.status === 'eligible'
        ? 'Your citizenship is accepted.'
        : `Your citizenship isn't among those accepted (${required}).`
    }
    case 'ELIG-WA-001':
    case 'ELIG-WA-002':
    case 'ELIG-WA-003':
    case 'ELIG-WA-004':
    case 'ELIG-WA-005':
      // These reasons are already written in plain language from the owner's own answers.
      return result.reason
    default:
      return "This requirement isn't checked automatically. Verify it yourself."
  }
}
