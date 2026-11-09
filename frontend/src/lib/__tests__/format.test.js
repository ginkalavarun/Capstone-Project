/**
 * Money + timestamp display (D3/D26 integer cents; D33 aware UTC).
 * The display layer must never invent values: only reformat.
 */
import { describe, expect, it } from 'vitest'
import { money, formatDateTime, timeAgo } from '../format.js'

describe('money', () => {
  it('renders integer cents as EUR', () => {
    expect(money(0)).toBe('€0.00')
    expect(money(250)).toBe('€2.50')
    expect(money(1450)).toBe('€14.50')
    expect(money(123456)).toBe('€1,234.56')
  })

  it('handles negative values (display only) and non-numbers defensively', () => {
    expect(money(-250)).toBe('-€2.50')
    expect(money(null)).toBe('€0.00')
    expect(money(undefined)).toBe('€0.00')
  })
})

describe('formatDateTime', () => {
  it('renders ISO-8601 strings and shows an em-dash for missing values', () => {
    expect(formatDateTime(null)).toBe('—')
    expect(formatDateTime('2026-11-07T18:03:12+00:00')).toMatch(/2026|Nov/i)
  })
})

describe('timeAgo', () => {
  it('describes recent and older moments', () => {
    expect(timeAgo(new Date().toISOString())).toBe('just now')
    expect(timeAgo(new Date(Date.now() - 12 * 60000).toISOString())).toBe('12 min ago')
    expect(timeAgo(new Date(Date.now() - 3 * 3600000).toISOString())).toBe('3 h ago')
    expect(timeAgo(null)).toBe('')
  })
})
