import { describe, expect, it } from 'vitest'
import { money, rtext, price, toneOf } from './format'

describe('format', () => {
  it('money', () => {
    expect(money(1234.4)).toBe('+$1,234')
    expect(money(-5)).toBe('−$5')
    expect(money(0)).toBe('$0')
    expect(money(null)).toBe('—')
    expect(money(undefined)).toBe('—')
    expect(money(0.2)).toBe('$0')
    expect(money(1234.4, { sign: false })).toBe('$1,234')
    expect(money(-1234.6, { sign: false })).toBe('−$1,235')
  })
  it('rtext', () => {
    expect(rtext(-0.5)).toBe('−0.50R')
    expect(rtext(1.234)).toBe('+1.23R')
    expect(rtext(0)).toBe('0.00R')
    expect(rtext(null)).toBe('—')
  })
  it('price', () => {
    expect(price(4012.5)).toBe('4,012.50')
    expect(price(null)).toBe('—')
  })
  it('toneOf', () => {
    expect(toneOf(1)).toBe('up')
    expect(toneOf(-1)).toBe('dn')
    expect(toneOf(0)).toBe('')
    expect(toneOf(null)).toBe('')
  })
})
