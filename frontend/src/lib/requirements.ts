import type {
  AppliesAt,
  EducationLevel,
  RequirementInput,
  RequirementType,
} from '../api/schemas'
import { orNull, parseCountries } from './forms'

// A canonical Requirement and a RequirementCandidate share this shape; toRow() accepts either.
interface RequirementLike {
  id: string
  requirement_type: RequirementType
  value: Record<string, unknown>
  applies_at: AppliesAt
  reference_date: string | null
  source_text: string | null
}

/** Editable form state for one structured requirement (the API's value shapes, flattened). */
export interface RequirementRow {
  key: string
  type: RequirementType
  years: string
  levels: EducationLevel[]
  acceptsIncoming: boolean
  countries: string
  description: string
  appliesAt: AppliesAt
  referenceDate: string
  sourceText: string
}

let nextKey = 0

export function newRequirementRow(type: RequirementType = 'minimum_age'): RequirementRow {
  nextKey += 1
  return {
    key: `new-${nextKey}`,
    type,
    years: '',
    levels: [],
    acceptsIncoming: false,
    countries: '',
    description: '',
    appliesAt: 'program_start',
    referenceDate: '',
    sourceText: '',
  }
}

export function toRow(requirement: RequirementLike): RequirementRow {
  const value = requirement.value
  const row = newRequirementRow(requirement.requirement_type)
  return {
    ...row,
    key: requirement.id,
    years: typeof value.years === 'number' ? String(value.years) : '',
    levels: Array.isArray(value.levels) ? (value.levels as EducationLevel[]) : [],
    acceptsIncoming: value.accepts_incoming === true,
    countries: Array.isArray(value.countries) ? value.countries.join(', ') : '',
    description: typeof value.description === 'string' ? value.description : '',
    appliesAt: requirement.applies_at,
    referenceDate: requirement.reference_date ?? '',
    sourceText: requirement.source_text ?? '',
  }
}

function valueFor(row: RequirementRow): Record<string, unknown> {
  switch (row.type) {
    case 'minimum_age':
      // Sent as typed; the backend rejects a missing or non-integer age with a clear error.
      return { years: row.years.trim() === '' ? null : Number(row.years) }
    case 'education':
      return { levels: row.levels, accepts_incoming: row.acceptsIncoming }
    case 'citizenship':
      return { countries: parseCountries(row.countries) ?? [] }
    default:
      return { description: row.description.trim() }
  }
}

export function toRequirementInput(row: RequirementRow): RequirementInput {
  const dated = row.type === 'minimum_age' || row.type === 'education'
  const appliesAt = dated ? row.appliesAt : 'program_start'
  return {
    requirement_type: row.type,
    value: valueFor(row),
    applies_at: appliesAt,
    reference_date: appliesAt === 'explicit_date' ? orNull(row.referenceDate) : null,
    source_text: orNull(row.sourceText),
  }
}

/** The edited value/applies_at/reference_date for a requirement-review CandidateAccept (the
 * requirement type can't change, so it's never included here). */
export function toCandidateEdit(row: RequirementRow) {
  const { value, applies_at, reference_date } = toRequirementInput(row)
  return { value, applies_at, reference_date }
}

/** Human-readable structured value, for display only — never raw JSON. Shared by the
 * requirements list and the requirement review panel. */
export function describeValue(value: Record<string, unknown>): string {
  if (typeof value.years === 'number') return `at least ${value.years} years old`
  if (Array.isArray(value.levels)) {
    const levels = value.levels.join(' or ').replaceAll('_', ' ')
    return value.accepts_incoming ? `${levels} (incoming students accepted)` : levels
  }
  if (Array.isArray(value.countries)) return value.countries.join(', ')
  return typeof value.description === 'string' ? value.description : ''
}
