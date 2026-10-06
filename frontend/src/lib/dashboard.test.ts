import { describe, expect, it } from 'vitest'
import { barHeights, trendSummary } from './dashboard'

describe('barHeights', () => {
  it('is all zeros with no data, never NaN', () => {
    expect(barHeights([0, 0, 0])).toEqual([0, 0, 0])
    expect(barHeights([])).toEqual([])
    expect(barHeights([NaN, 2])).toEqual([0, 100])
  })
  it('scales to the largest week', () => {
    expect(barHeights([1, 2, 4])).toEqual([25, 50, 100])
  })
})

describe('trendSummary', () => {
  it('lists every week as text', () => {
    expect(trendSummary([{ week_start: '2041-03-04', count: 3 }])).toContain(
      '2041-03-04: 3',
    )
    expect(trendSummary([])).toBe('No weekly data')
  })
})
