import { AxeBuilder } from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { owner } from './env.ts'

// Milestone 19: axe on every route (synthetic data) and a horizontal-overflow check at five
// widths. Fails on serious/critical axe violations and on any page wider than its viewport.
test.describe.configure({ mode: 'serial' })

const run = Date.now()

const appRoutes = [
  '/dashboard',
  '/inbox',
  '/opportunities',
  '/opportunities/new',
  '/requirements',
  '/applications',
  '/profile',
  '/profile/match',
  '/profile/sources',
  '/sources',
]
const widths = [1440, 1280, 1024, 768, 390]

async function csrf(page: Page) {
  const session = await (await page.request.get('/api/auth/session')).json()
  return { 'X-CSRF-Token': session.csrf_token as string }
}

async function expectNoSeriousViolations(page: Page, label: string) {
  const { violations } = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  const serious = violations.filter(
    (v) => v.impact === 'serious' || v.impact === 'critical',
  )
  expect
    .soft(
      serious.map(
        (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`,
      ),
      label,
    )
    .toEqual([])
}

const overflow = (page: Page) =>
  page.evaluate<number>(
    'document.documentElement.scrollWidth - document.documentElement.clientWidth',
  )

test('public pages: landing and login', async ({ page }) => {
  for (const route of ['/', '/login']) {
    await page.goto(route)
    await page.waitForLoadState('networkidle')
    await expectNoSeriousViolations(page, route)
  }
})

test('authenticated routes: axe and overflow at five widths', async ({ page }) => {
  test.setTimeout(300_000)
  await page.goto('/login')
  await page.getByLabel('Username').fill(owner.username)
  await page.getByLabel('Password').fill(owner.password)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)

  const headers = await csrf(page)
  const created = await page.request.post('/api/opportunities', {
    headers,
    data: {
      title: `Synthetic A11y Role With A Deliberately Long Title For Narrow Columns ${run}`,
      organization: `Example A11y Organization With A Long Name ${run}`,
      opportunity_type: 'internship',
      description: 'Applicants must be at least 16 years old.',
      requirements_assessment_status: 'unassessed',
      requirements: [],
    },
  })
  expect(created.status()).toBe(201)
  const opportunityId = (await created.json()).id as string
  await page.request.post(
    `/api/opportunities/${opportunityId}/requirement-review/refresh`,
    { headers },
  )
  const tracked = await page.request.put(
    `/api/opportunities/${opportunityId}/application`,
    {
      headers,
      data: {
        status: 'applied',
        next_action: 'Follow up',
        next_action_due: '2030-01-01',
      },
    },
  )
  expect(tracked.ok()).toBe(true)

  const routes = [...appRoutes, `/opportunities/${opportunityId}`]
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 })
    for (const route of routes) {
      await page.goto(route)
      await page.waitForLoadState('networkidle')
      const label = `${route} @${width}`
      expect.soft(await overflow(page), `overflow ${label}`).toBeLessThanOrEqual(0)
      if (width === 1280 || width === 390) await expectNoSeriousViolations(page, label)
    }
  }

  // The pipeline view at tablet and phone widths.
  for (const width of [768, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/applications')
    await page.getByRole('tab', { name: 'Pipeline' }).click()
    await page.waitForLoadState('networkidle')
    expect
      .soft(await overflow(page), `pipeline overflow @${width}`)
      .toBeLessThanOrEqual(0)
    await expectNoSeriousViolations(page, `pipeline @${width}`)
  }
})
