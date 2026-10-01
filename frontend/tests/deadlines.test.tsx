import { describe, expect, it } from 'vitest'
import {
  daysUntil,
  isClosingSoon,
  isDeadlinePassed,
  localToday,
} from '../src/lib/deadlines'

// Pure date math (ADR-012 §14): fixed dates only, never the real clock.

describe('daysUntil', () => {
  it('is zero for today', () => {
    expect(daysUntil('2041-03-10', '2041-03-10')).toBe(0)
  })

  it('counts forward and backward', () => {
    expect(daysUntil('2041-03-17', '2041-03-10')).toBe(7)
    expect(daysUntil('2041-03-03', '2041-03-10')).toBe(-7)
  })

  it('crosses a month boundary', () => {
    expect(daysUntil('2041-04-02', '2041-03-30')).toBe(3)
  })

  it('crosses a year boundary', () => {
    expect(daysUntil('2042-01-02', '2041-12-30')).toBe(3)
  })
})

describe('isClosingSoon', () => {
  it('is true for today through 7 days out', () => {
    expect(isClosingSoon('2041-03-10', '2041-03-10')).toBe(true)
    expect(isClosingSoon('2041-03-17', '2041-03-10')).toBe(true)
  })

  it('is false at 8 days out', () => {
    expect(isClosingSoon('2041-03-18', '2041-03-10')).toBe(false)
  })

  it('is false once the deadline has passed', () => {
    expect(isClosingSoon('2041-03-09', '2041-03-10')).toBe(false)
  })

  it('is false for a null deadline', () => {
    expect(isClosingSoon(null, '2041-03-10')).toBe(false)
  })
})

describe('isDeadlinePassed', () => {
  it('is true strictly before today', () => {
    expect(isDeadlinePassed('2041-03-09', '2041-03-10')).toBe(true)
  })

  it('is false on or after today', () => {
    expect(isDeadlinePassed('2041-03-10', '2041-03-10')).toBe(false)
    expect(isDeadlinePassed('2041-03-11', '2041-03-10')).toBe(false)
  })

  it('is false for a null deadline', () => {
    expect(isDeadlinePassed(null, '2041-03-10')).toBe(false)
  })
})

describe('localToday', () => {
  it('returns the local calendar date as YYYY-MM-DD', () => {
    expect(localToday()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})
