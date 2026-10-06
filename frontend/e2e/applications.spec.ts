import { expect, test, type Page } from '@playwright/test'
import { owner } from './env.ts'

// ADR-025: the application lifecycle with history, and the home dashboard (synthetic data only).

const pad = (n: number) => String(n).padStart(2, '0')
function localDate(offsetDays = 0): string {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Username').fill(owner.username)
  await page.getByLabel('Password').fill(owner.password)
  await page.getByRole('button', { name: 'Log in' }).click()
  // The post-login landing page is the dashboard.
  await expect(page).toHaveURL(/\/dashboard$/)
}

async function addOpportunity(page: Page, title: string, organization: string) {
  await page.goto('/opportunities/new')
  await page.getByLabel('Title (required)').fill(title)
  await page.getByLabel('Organization (required)').fill(organization)
  await page.getByLabel('Type').first().selectOption('internship')
  await page.getByRole('button', { name: 'Save opportunity' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(title)
  return page.url()
}

test('application lifecycle: save, start, applied, follow-up, interview, offer, accept, history', async ({
  page,
}) => {
  const stamp = Date.now()
  const title = `E2E Lifecycle Role ${stamp}`
  const org = `Lifecycle Org ${stamp}`
  await login(page)
  const url = await addOpportunity(page, title, org)

  await page.getByRole('button', { name: 'Track this opportunity' }).click()
  await expect(page.getByText('Now tracking this opportunity.')).toBeVisible()

  // The workspace: filter to this company and walk it through the stages.
  await page
    .getByRole('navigation', { name: 'Main' })
    .getByRole('link', { name: 'Applications' })
    .click()
  await page.getByRole('searchbox', { name: 'Company' }).fill(org)
  const card = page.getByRole('listitem').filter({ hasText: title })
  const stage = card.getByLabel(`Stage for ${title}`)
  await expect(stage).toHaveValue('saved')

  await card.getByRole('button', { name: 'Start application' }).click()
  await expect(stage).toHaveValue('applying')
  await card.getByRole('button', { name: 'Mark applied' }).click()
  await expect(stage).toHaveValue('applied')

  await card.getByRole('button', { name: 'Schedule follow-up' }).click()
  await card.getByLabel('Follow-up date').fill(localDate(5))
  await card.getByRole('button', { name: 'Save follow-up' }).click()
  await expect(card).toContainText(`due ${localDate(5)}`)

  await card.getByRole('button', { name: 'Add interview' }).click()
  await card.getByLabel(/Interview date and time/).fill(`${localDate(7)}T10:30`)
  await card.getByRole('button', { name: 'Save interview' }).click()
  await expect(stage).toHaveValue('interview')
  await expect(card).toContainText('Interview')

  await card.getByRole('button', { name: 'Mark offer' }).click()
  await expect(stage).toHaveValue('offer')
  await card.getByRole('button', { name: 'Accept' }).click()
  await expect(stage).toHaveValue('accepted')

  // The pipeline view puts it in the Outcome column.
  await page.getByRole('tab', { name: 'Pipeline' }).click()
  await expect(
    page.getByRole('region', { name: 'Outcome column' }).getByText(title),
  ).toBeVisible()

  // The detail page shows the recorded history.
  await page.goto(url)
  const history = page.getByRole('region', { name: 'History' })
  await expect(history).toContainText('Started tracking as Saved')
  await expect(history).toContainText('Status: Saved → Applying')
  await expect(history).toContainText('Status: Applying → Applied')
  await expect(history).toContainText('Follow-up date changed')
  await expect(history).toContainText('Interview scheduled')
  await expect(history).toContainText('Offer received')
  await expect(history).toContainText('Status: Offer → Accepted')
  // applied_at was stamped when it became applied.
  await expect(page.getByLabel('Applied at')).not.toHaveValue('')
})

test('dashboard shows a due follow-up and never a hidden opportunity', async ({
  page,
}) => {
  const stamp = Date.now()
  const visible = `E2E Dashboard Visible ${stamp}`
  const hidden = `E2E Dashboard Hidden ${stamp}`
  await login(page)

  const track = async (title: string) => {
    const url = await addOpportunity(page, title, `Dashboard Org ${stamp}`)
    await page.getByRole('button', { name: 'Track this opportunity' }).click()
    await expect(page.getByText('Now tracking this opportunity.')).toBeVisible()
    await page.getByLabel('Status').selectOption('applied')
    await page.getByLabel('Next action', { exact: true }).fill('Email the recruiter')
    await page.getByLabel('Next action due').fill(localDate(0))
    await page.getByRole('button', { name: 'Save application' }).click()
    await expect(page.getByText('Application tracking saved.')).toBeVisible()
    return url
  }
  await track(visible)
  await track(hidden)
  await page.getByRole('button', { name: 'Hide' }).click()
  await expect(page.getByRole('button', { name: 'Unhide' })).toBeVisible()

  await page
    .getByRole('navigation', { name: 'Main' })
    .getByRole('link', { name: 'Dashboard' })
    .click()
  const actions = page.getByRole('region', { name: /Action required/ })
  await expect(actions.getByRole('link', { name: visible })).toBeVisible()
  await expect(actions).toContainText('Email the recruiter')
  await expect(page.getByText(hidden)).toHaveCount(0)

  // Counts never render NaN, whatever the data.
  await expect(page.locator('body')).not.toContainText(/NaN|Infinity/)
  const pipeline = page.getByRole('region', { name: 'Application pipeline' })
  await expect(pipeline.getByRole('link', { name: 'Applied' })).toBeVisible()
})
