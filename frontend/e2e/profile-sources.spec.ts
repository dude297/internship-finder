import { expect, test, type Page } from '@playwright/test'
import { scoreBreakdownSchema, type ScoreBreakdown } from '../src/api/schemas.ts'
import { owner } from './env.ts'
import { makeTextPdf } from './fixtures/make-pdf.ts'

// Profile source ingestion (ADR-011): upload a synthetic résumé, confirm pending facts never
// affect fit, review (accept/edit/reject) and apply once, confirm the fit score and "Why this
// match" pick up the accepted skill, confirm review state persists across a re-login, then
// delete the source and confirm fit falls back while the manual Match Profile skill survives.
// Every name and file body is unique per run (Date.now()), so re-uploading is never a same-bytes
// 409 and search filters isolate this run's data on a reused database.

const run = Date.now()
const importedSkill = `Synthskill${run}`
const manualSkill = `Manualskill${run}`
const projectName = `Synthetic Import Project ${run}`
const awardName = `Synthetic Import Award ${run}`
const titleA = `Synthetic Source Role A ${run}`
const titleB = `Synthetic Source Role B ${run}`
const resumeFilename = `synthetic-resume-${run}.txt`
const pdfSkill = `Synthpdfskill${run}`
const pdfFilename = `synthetic-resume-${run}.pdf`

function resumeText(): string {
  return [
    'Synthetic Applicant',
    'synthetic.applicant@example.com',
    '',
    'Skills',
    importedSkill,
    '',
    'Projects',
    projectName,
    `- Built a synthetic prototype for run ${run}.`,
    '',
    'Awards',
    awardName,
    '',
  ].join('\n')
}

async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Username').fill(owner.username)
  await page.getByLabel('Password').fill(owner.password)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page).not.toHaveURL(/\/login$/)
}

/** Create an opportunity through the same-origin API (the browser's session and CSRF token). */
async function createOpportunity(
  page: Page,
  body: Record<string, unknown>,
): Promise<string> {
  const session = await (await page.request.get('/api/auth/session')).json()
  const response = await page.request.post('/api/opportunities', {
    headers: { 'X-CSRF-Token': session.csrf_token },
    data: {
      organization: 'Example Institute',
      opportunity_type: 'internship',
      start_date: '2041-06-20',
      requirements: [],
      ...body,
    },
  })
  expect(response.status()).toBe(201)
  return (await response.json()).id as string
}

async function fitBreakdown(page: Page, id: string): Promise<ScoreBreakdown | null> {
  const response = await page.request.get(`/api/opportunities/${encodeURIComponent(id)}`)
  expect(response.status()).toBe(200)
  const body = await response.json()
  const raw = body.latest_evaluation?.score_breakdown
  return raw ? scoreBreakdownSchema.parse(raw) : null
}

async function goToSources(page: Page) {
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Profile', exact: true }).click()
  await page.getByRole('link', { name: 'Imported Profile', exact: true }).click()
}

test('profile sources: pending has no effect, review + apply rescoring, persistence, delete falls back', async ({
  page,
}) => {
  await login(page)

  // A manual Match Profile skill, unrelated to the résumé about to be uploaded.
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Profile', exact: true }).click()
  await page.getByRole('link', { name: 'Match Profile' }).click()
  await page.getByLabel('Skills', { exact: true }).fill(manualSkill)
  await page.getByLabel('Skills', { exact: true }).press('Enter')
  await page.getByRole('button', { name: 'Save Match Profile' }).click()
  await expect(page.getByText(/Match Profile saved\./)).toBeVisible()

  // Two eligible, requirements-complete postings: A mentions the résumé skill, B doesn't.
  const complete = { requirements_assessment_status: 'complete' }
  const idA = await createOpportunity(page, {
    title: titleA,
    description: `Looking for ${importedSkill} and ${manualSkill} experience.`,
    ...complete,
  })
  const idB = await createOpportunity(page, {
    title: titleB,
    description: `Looking for ${manualSkill} experience only.`,
    ...complete,
  })

  const beforeUploadA = await fitBreakdown(page, idA)
  expect(beforeUploadA).not.toBeNull()

  // Upload the synthetic résumé via the file input.
  await goToSources(page)
  await page.locator('#resume-file').setInputFiles({
    name: resumeFilename,
    mimeType: 'text/plain',
    buffer: Buffer.from(resumeText(), 'utf-8'),
  })
  await page.getByRole('button', { name: 'Upload', exact: true }).click()
  await expect(page.getByText(/waiting for review/)).toBeVisible()
  await expect(
    page.getByText(/Imported facts never affect matching until you accept them/),
  ).toBeVisible()

  const sourceItem = page.getByRole('listitem').filter({ hasText: resumeFilename })
  await expect(sourceItem).toBeVisible()
  await expect(sourceItem.getByText('Pending 3')).toBeVisible()
  await expect(sourceItem.getByText('Accepted 0')).toBeVisible()
  await expect(sourceItem.getByText('Rejected 0')).toBeVisible()

  // Pending facts score nothing: A's breakdown is untouched, and the imported skill isn't
  // counted, so A doesn't outrank B on its account.
  const afterUploadA = await fitBreakdown(page, idA)
  expect(afterUploadA).toEqual(beforeUploadA)
  expect(afterUploadA?.components?.technical?.matched ?? []).not.toContain(importedSkill)

  // Review: accept the skill as-is, accept the project but edit its description, reject the
  // award. Apply once. (Uploading already left the facts panel open.)
  const skillItem = sourceItem.getByRole('listitem').filter({ hasText: importedSkill })
  await skillItem.getByRole('button', { name: 'Accept' }).click()

  const projectItem = sourceItem.getByRole('listitem').filter({ hasText: projectName })
  await projectItem.getByRole('button', { name: 'Accept' }).click()
  const editedDescription = `Edited: rebuilt the synthetic prototype for run ${run}.`
  await projectItem
    .getByLabel(new RegExp(`Description for ${projectName}`))
    .fill(editedDescription)

  const awardItem = sourceItem.getByRole('listitem').filter({ hasText: awardName })
  await awardItem.getByRole('button', { name: 'Reject' }).click()

  await sourceItem.getByRole('button', { name: /^Apply \d+ change/ }).click()
  await expect(sourceItem.getByText(/Scoring refreshed/)).toBeVisible()
  await expect(sourceItem.getByText('Pending 0')).toBeVisible()
  await expect(sourceItem.getByText('Accepted 2')).toBeVisible()
  await expect(sourceItem.getByText('Rejected 1')).toBeVisible()
  await expect(sourceItem.getByText(editedDescription)).toBeVisible()

  // A's fit increased and now matches the accepted skill; B is unaffected.
  const afterAcceptA = await fitBreakdown(page, idA)
  expect(afterAcceptA?.components?.technical?.matched ?? []).toContain(importedSkill)
  expect(afterAcceptA?.score).toBeGreaterThan(beforeUploadA?.score ?? 0)
  const afterAcceptB = await fitBreakdown(page, idB)
  expect(afterAcceptB?.components?.technical?.matched ?? []).not.toContain(importedSkill)

  // Recommended order: A (matches both Match Profile skills) ranks above B (matches one).
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Opportunities', exact: true }).click()
  await page.getByLabel('Search title or organization').fill(String(run))
  await page.getByRole('button', { name: 'Search' }).click()
  await expect(page.getByRole('status')).toHaveText('Showing 1–2 of 2')
  await expect(page.getByLabel('Sort')).toHaveValue('recommended')
  expect(await page.locator('main ul > li h2').allTextContents()).toEqual([
    titleA,
    titleB,
  ])

  // Why this match mentions the newly accepted skill.
  await page.getByRole('link', { name: titleA }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(titleA)
  const why = page.getByRole('region', { name: /Why this match/ })
  await expect(why).toContainText(importedSkill)

  // Log out and back in: review state persists.
  await page.getByRole('button', { name: 'Log out' }).click()
  await expect(page).toHaveURL(/\/login$/)
  await login(page)
  await goToSources(page)
  const sourceItemAgain = page.getByRole('listitem').filter({ hasText: resumeFilename })
  await expect(sourceItemAgain.getByText('Accepted 2')).toBeVisible()
  await expect(sourceItemAgain.getByText('Rejected 1')).toBeVisible()
  await expect(sourceItemAgain.getByText('Pending 0')).toBeVisible()

  // Delete the source, confirming the dialog.
  page.once('dialog', (dialog) => void dialog.accept())
  await sourceItemAgain.getByRole('button', { name: 'Delete' }).click()
  await expect(page.getByText(/Scoring refreshed|Matching unchanged/)).toBeVisible()
  await expect(
    page.getByRole('listitem').filter({ hasText: resumeFilename }),
  ).toHaveCount(0)

  // A's fit falls back to pre-import: the imported skill no longer matches, but the manual
  // skill still does.
  const afterDeleteA = await fitBreakdown(page, idA)
  expect(afterDeleteA).toEqual(beforeUploadA)
  expect(afterDeleteA?.components?.technical?.matched ?? []).not.toContain(importedSkill)
  expect(afterDeleteA?.components?.technical?.matched ?? []).toContain(manualSkill)

  // The manual Match Profile skill was never touched by the source's deletion.
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Profile', exact: true }).click()
  await page.getByRole('link', { name: 'Match Profile' }).click()
  await expect(page.getByRole('button', { name: `Remove ${manualSkill}` })).toBeVisible()
})

test('profile sources: PDF upload is parsed into pending facts', async ({ page }) => {
  await login(page)
  await goToSources(page)

  const pdfBytes = makeTextPdf(['Synthetic PDF Applicant', 'Skills', pdfSkill])
  await page
    .locator('#resume-file')
    .setInputFiles({ name: pdfFilename, mimeType: 'application/pdf', buffer: pdfBytes })
  await page.getByRole('button', { name: 'Upload', exact: true }).click()
  await expect(page.getByText(/waiting for review/)).toBeVisible()

  const pdfItem = page.getByRole('listitem').filter({ hasText: pdfFilename })
  await expect(pdfItem).toBeVisible()
  await expect(pdfItem).toContainText('PDF')
  await expect(pdfItem.getByText('Pending 1')).toBeVisible()
  // Uploading already left the facts panel open.
  await expect(pdfItem.getByText(pdfSkill)).toBeVisible()

  // Clean up without accepting anything, so this source never affects fit.
  page.once('dialog', (dialog) => void dialog.accept())
  await pdfItem.getByRole('button', { name: 'Delete' }).click()
  await expect(page.getByRole('listitem').filter({ hasText: pdfFilename })).toHaveCount(0)
})
