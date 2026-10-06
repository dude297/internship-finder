import { expect, test, type Page } from '@playwright/test'
import { owner } from './env.ts'

// ADR-024 scenario: the global requirement review queue. Five synthetic opportunities each get
// one suggestion; the owner accepts one, rejects one by keyboard, edits and accepts one, skips
// one, and batch-rejects the rest. The unique run id in the organization name keeps this
// repeatable against a reused E2E database that already holds other pending suggestions.
test.describe.configure({ mode: 'serial' })

const run = Date.now()
const organization = `Example Queue Org ${run}`
const titles = ['Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo'].map(
  (name) => `Synthetic Queue ${name} ${run}`,
)
const ids: Record<string, string> = {}

async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Username').fill(owner.username)
  await page.getByLabel('Password').fill(owner.password)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page).not.toHaveURL(/\/login$/)
}

async function csrf(page: Page) {
  const session = await (await page.request.get('/api/auth/session')).json()
  return { 'X-CSRF-Token': session.csrf_token as string }
}

async function requirementYears(page: Page, title: string) {
  const detail = await (await page.request.get(`/api/opportunities/${ids[title]}`)).json()
  return (detail.requirements as { value: { years?: number } }[]).map(
    (r) => r.value.years,
  )
}

test('review queue: accept, reject, edit, skip, and batch reject', async ({ page }) => {
  await login(page)
  const headers = await csrf(page)

  for (const title of titles) {
    const created = await page.request.post('/api/opportunities', {
      headers,
      data: {
        title,
        organization,
        opportunity_type: 'internship',
        description: 'Applicants must be at least 16 years old.',
        requirements_assessment_status: 'unassessed',
        requirements: [],
      },
    })
    expect(created.status()).toBe(201)
    const opportunity = await created.json()
    ids[title] = opportunity.id
    const refreshed = await page.request.post(
      `/api/opportunities/${opportunity.id}/requirement-review/refresh`,
      { headers },
    )
    expect(refreshed.ok()).toBe(true)
  }

  // The Inbox links into the queue.
  await page.getByRole('link', { name: 'Inbox', exact: true }).click()
  await page.getByRole('link', { name: 'Review requirement suggestions' }).click()
  await expect(page).toHaveURL(/\/requirements$/)
  await expect(page.getByRole('heading', { name: 'Review', level: 1 })).toBeVisible()
  await expect(page.getByText('Shortcuts:')).toBeVisible()

  await page.getByLabel('Organization contains').fill(String(run))
  await page.getByRole('button', { name: 'Apply filters' }).click()
  const loaded = page.getByRole('region', { name: 'Loaded suggestions' })
  await expect(loaded.getByRole('heading', { name: /\(5 of 5\)/ })).toBeVisible()

  const card = page.getByRole('region', { name: 'Current suggestion' })
  const open = (title: string) =>
    loaded.getByRole('button', { name: new RegExp(`${title}`) }).click()

  // Accept (button).
  await open(titles[0])
  await expect(card.getByRole('heading', { name: titles[0] })).toBeVisible()
  await expect(card.locator('mark')).toHaveText(
    'Applicants must be at least 16 years old.',
  )
  await card.getByRole('button', { name: 'Accept', exact: true }).click()
  await expect(page.getByText('Accepted.', { exact: true })).toBeVisible()
  await expect(loaded.getByRole('heading', { name: /\(4 of 4\)/ })).toBeVisible()
  expect(await requirementYears(page, titles[0])).toEqual([16])

  // Reject (keyboard).
  await open(titles[1])
  await expect(card.getByRole('heading', { name: titles[1] })).toBeVisible()
  await page.keyboard.press('r')
  await expect(page.getByText('Rejected.', { exact: true })).toBeVisible()
  await expect(loaded.getByRole('heading', { name: /\(3 of 3\)/ })).toBeVisible()
  expect(await requirementYears(page, titles[1])).toEqual([])

  // Edit + Accept: the edited value, not the suggestion's, becomes the requirement. The
  // shortcut is off while typing in the field.
  await open(titles[2])
  await expect(card.getByRole('heading', { name: titles[2] })).toBeVisible()
  await page.keyboard.press('e')
  const years = card.getByLabel('Minimum age (years)')
  await years.fill('18')
  await years.press('r') // typing: must not reject
  await card.getByRole('button', { name: 'Save edit and accept' }).click()
  await expect(page.getByText('Accepted with your edit.')).toBeVisible()
  await expect(loaded.getByRole('heading', { name: /\(2 of 2\)/ })).toBeVisible()
  expect(await requirementYears(page, titles[2])).toEqual([18])

  // Skip leaves it pending and moves on.
  await open(titles[3])
  await card.getByRole('button', { name: 'Skip' }).click()
  await expect(loaded.getByRole('heading', { name: /\(2 of 2\)/ })).toBeVisible()
  await expect(loaded.getByText(/skipped/)).toBeVisible()

  // Batch reject the two that are left, only after confirming.
  await loaded.getByRole('button', { name: 'Select all loaded' }).click()
  await loaded.getByRole('button', { name: 'Reject selected (2)' }).click()
  await loaded.getByRole('button', { name: 'Confirm reject' }).click()
  await expect(page.getByText('Rejected 2 suggestions.')).toBeVisible()
  await expect(page.getByText(/Nothing to review|No suggestions match/)).toBeVisible()
  expect(await requirementYears(page, titles[3])).toEqual([])
  expect(await requirementYears(page, titles[4])).toEqual([])
})
