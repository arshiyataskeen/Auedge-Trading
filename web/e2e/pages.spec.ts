import { expect, test, type Page } from '@playwright/test'

// GET-only flows against the running server (never click anything that POSTs).
const ROUTES = ['dashboard', 'trade', 'backtest', 'journal', 'demo', 'demo/calendar', 'news', 'agents']
const NAV = ['Dashboard', 'Trade', 'Backtest', 'Journal', 'Demo', 'News', 'Agents']

function watchErrors(page: Page) {
  const errors: string[] = []
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  page.on('pageerror', (e) => errors.push(String(e)))
  return errors
}
async function settle(page: Page) {
  await expect(page.locator('main#page')).toBeVisible()
  await page.waitForLoadState('networkidle').catch(() => {})
}

test.describe('pages', () => {
  for (const r of ROUTES) {
    test(`${r} shows one main panel and no console errors`, async ({ page }) => {
      const errors = watchErrors(page)
      await page.goto(`/app/${r}`)
      await settle(page)
      await expect(page.locator('h1').first()).toBeVisible()
      const lists = await page.locator('[role=tablist]:visible').count()
      if (lists > 0) {
        await expect(page.locator('[role=tabpanel]:visible')).toHaveCount(lists)
      }
      expect(errors).toEqual([])
    })
  }

  test('every sidebar link loads its page', async ({ page }) => {
    const errors = watchErrors(page)
    await page.goto('/app/dashboard')
    await settle(page)
    for (const name of NAV) {
      await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name }).click()
      await expect(page).toHaveURL(new RegExp(`/app/${name.toLowerCase()}`))
      await expect(page.locator('h1').first()).toBeVisible()
    }
    expect(errors).toEqual([])
  })

  test('375 px has no horizontal scroll on any page', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 })
    for (const r of ROUTES) {
      await page.goto(`/app/${r}`)
      await settle(page)
      await page.waitForTimeout(500)
      const over = await page.evaluate(() => {
        const m = document.getElementById('page')!
        return {
          doc: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          main: m.scrollWidth - m.clientWidth,
        }
      })
      expect(over, r).toEqual({ doc: 0, main: 0 })
    }
  })

  test('light/dark toggle works and persists across reload', async ({ page }) => {
    await page.goto('/app/dashboard')
    await settle(page)
    const theme = () => page.evaluate(() => document.documentElement.dataset.theme === 'light' ? 'light' : 'dark')
    const before = await theme()
    await page.getByRole('button', { name: 'Toggle theme' }).click()
    const after = await theme()
    expect(after).not.toBe(before)
    await page.reload()
    await settle(page)
    expect(await theme()).toBe(after)
    await page.getByRole('button', { name: 'Toggle theme' }).click()
    expect(await theme()).toBe(before)
  })

  test('Escape closes modals', async ({ page }) => {
    await page.goto('/app/journal')
    await settle(page)
    const open = page.getByRole('button', { name: /new account|add account|＋/i }).first()
    await expect(open).toBeVisible()
    await open.click()
    const dlg = page.getByRole('dialog')
    await expect(dlg).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(dlg).toHaveCount(0)
  })
})

test.describe("backtest", () => {
  test.use({ actionTimeout: 5000 })
  test('month → day → replay', async ({ page }) => {
    await page.goto('/app/backtest')
    await settle(page)
    const month = page.locator('tr[data-month]').first()
    await expect(month).toBeVisible({ timeout: 15000 })
    await month.click()
    const day = page.getByRole('region', { name: 'Day by day' }).locator('button[data-day]').first()
    // the newest month starts open; a click toggles it, so click again if it just closed
    if (!(await day.isVisible())) await month.click()
    await expect(day).toBeVisible()
    await day.click()
    const trade = page.locator('button[data-ti]').first()
    await expect(trade).toBeVisible()
    await trade.click()
    const dlg = page.getByRole('dialog', { name: 'Trade replay' })
    await expect(dlg).toBeVisible()
    await expect(dlg.locator('canvas').first()).toBeVisible({ timeout: 15000 })
    await expect(dlg.getByRole('alert')).toHaveCount(0)
    await page.keyboard.press('Escape')
    await expect(dlg).toHaveCount(0)
  })

  test('scroll position is stable while data loads', async ({ page }) => {
    await page.goto('/app/backtest')
    await page.locator('main#page').waitFor()
    await page.evaluate(() => { document.getElementById('page')!.scrollTop = 600 })
    const t0 = await page.evaluate(() => document.getElementById('page')!.scrollTop)
    await page.waitForTimeout(3000)
    const t1 = await page.evaluate(() => document.getElementById('page')!.scrollTop)
    expect(Math.abs(t1 - t0)).toBeLessThan(5)
  })
})
