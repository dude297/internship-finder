import {
  appliesAtValues,
  educationLevels,
  requirementTypes,
  type AppliesAt,
  type EducationLevel,
  type RequirementType,
} from '../api/schemas'
import type { RequirementRow } from '../lib/requirements'
import {
  appliesAtLabels,
  educationLevelLabels,
  requirementTypeLabels,
} from '../lib/labels'
import { dangerButtonClass, inputClass, secondaryButtonClass } from '../lib/styles'
import { Field } from './ui'
import { newRequirementRow } from '../lib/requirements'

// Only age and education rules use a reference date; the others ignore "applies at".
const DATED: RequirementType[] = ['minimum_age', 'education']

export function RequirementsEditor({
  rows,
  onChange,
}: {
  rows: RequirementRow[]
  onChange: (rows: RequirementRow[]) => void
}) {
  const update = (key: string, changes: Partial<RequirementRow>) =>
    onChange(rows.map((row) => (row.key === key ? { ...row, ...changes } : row)))

  return (
    <div className="space-y-3">
      {rows.length === 0 && (
        <p className="text-sm text-slate-600">No requirements recorded.</p>
      )}
      {rows.map((row, index) => {
        const id = (name: string) => `req-${row.key}-${name}`
        return (
          <fieldset
            key={row.key}
            className="space-y-2 rounded border border-slate-200 p-3"
          >
            <legend className="px-1 text-sm font-medium">Requirement {index + 1}</legend>
            <Field id={id('type')} label="Type">
              <select
                id={id('type')}
                value={row.type}
                onChange={(e) =>
                  update(row.key, { type: e.target.value as RequirementType })
                }
                className={inputClass}
              >
                {requirementTypes.map((type) => (
                  <option key={type} value={type}>
                    {requirementTypeLabels[type]}
                  </option>
                ))}
              </select>
            </Field>

            {row.type === 'minimum_age' && (
              <Field id={id('years')} label="Minimum age (years)">
                <input
                  id={id('years')}
                  type="number"
                  min={0}
                  max={120}
                  value={row.years}
                  onChange={(e) => update(row.key, { years: e.target.value })}
                  className={inputClass}
                />
              </Field>
            )}

            {row.type === 'education' && (
              <>
                <fieldset>
                  <legend className="text-sm font-medium">Accepted level(s)</legend>
                  {educationLevels.map((level: EducationLevel) => (
                    <label
                      key={level}
                      className="mr-4 inline-flex items-center gap-1 text-sm"
                    >
                      <input
                        type="checkbox"
                        checked={row.levels.includes(level)}
                        onChange={(e) =>
                          update(row.key, {
                            levels: e.target.checked
                              ? [...row.levels, level]
                              : row.levels.filter((l) => l !== level),
                          })
                        }
                      />
                      {educationLevelLabels[level]}
                    </label>
                  ))}
                </fieldset>
                <label className="inline-flex items-center gap-1 text-sm">
                  <input
                    type="checkbox"
                    checked={row.acceptsIncoming}
                    onChange={(e) =>
                      update(row.key, { acceptsIncoming: e.target.checked })
                    }
                  />
                  Incoming students accepted (finished the previous level, about to start)
                </label>
              </>
            )}

            {row.type === 'citizenship' && (
              <Field
                id={id('countries')}
                label="Accepted citizenship(s)"
                hint="Two-letter country codes separated by commas, for example: US"
              >
                <input
                  id={id('countries')}
                  value={row.countries}
                  onChange={(e) => update(row.key, { countries: e.target.value })}
                  aria-describedby={`${id('countries')}-hint`}
                  className={inputClass}
                />
              </Field>
            )}

            {(row.type === 'work_authorization' || row.type === 'other') && (
              <Field
                id={id('description')}
                label="Description"
                hint="Stored for reference. It isn't checked automatically and always needs verification."
              >
                <textarea
                  id={id('description')}
                  value={row.description}
                  onChange={(e) => update(row.key, { description: e.target.value })}
                  aria-describedby={`${id('description')}-hint`}
                  className={inputClass}
                />
              </Field>
            )}

            {DATED.includes(row.type) && (
              <div className="grid gap-2 sm:grid-cols-2">
                <Field id={id('applies')} label="Applies">
                  <select
                    id={id('applies')}
                    value={row.appliesAt}
                    onChange={(e) =>
                      update(row.key, { appliesAt: e.target.value as AppliesAt })
                    }
                    className={inputClass}
                  >
                    {appliesAtValues.map((value) => (
                      <option key={value} value={value}>
                        {appliesAtLabels[value]}
                      </option>
                    ))}
                  </select>
                </Field>
                {row.appliesAt === 'explicit_date' && (
                  <Field id={id('date')} label="Date">
                    <input
                      id={id('date')}
                      type="date"
                      value={row.referenceDate}
                      onChange={(e) => update(row.key, { referenceDate: e.target.value })}
                      className={inputClass}
                    />
                  </Field>
                )}
              </div>
            )}

            <Field id={id('source')} label="Text from the posting (optional)">
              <input
                id={id('source')}
                value={row.sourceText}
                onChange={(e) => update(row.key, { sourceText: e.target.value })}
                className={inputClass}
              />
            </Field>
            <button
              type="button"
              onClick={() => onChange(rows.filter((r) => r.key !== row.key))}
              className={dangerButtonClass}
            >
              Remove requirement {index + 1}
            </button>
          </fieldset>
        )
      })}
      <button
        type="button"
        onClick={() => onChange([...rows, newRequirementRow()])}
        className={secondaryButtonClass}
      >
        Add requirement
      </button>
    </div>
  )
}
