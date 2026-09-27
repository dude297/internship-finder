import type {
  AppliesAt,
  EducationLevel,
  Requirement,
  RequirementInput,
  RequirementType,
} from '../api/schemas'
import { orNull, parseCountries } from './forms'

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

export function toRow(requirement: Requirement): RequirementRow {
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
