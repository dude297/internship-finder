import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import {
  importedFact,
  json,
  loggedIn,
  mockApi,
  profileSource,
  profileSourceDetail,
  renderAt,
} from './helpers'

// Synthetic files and facts only.

function makeFile(name: string, type: string, size: number): File {
  const file = new File(['synthetic content'], name, { type })
  Object.defineProperty(file, 'size', { value: size })
  return file
}

describe('profile sources page', () => {
  it('lists uploaded files with review counts', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/profile/sources': () => [
        profileSource({ pending_count: 2, accepted_count: 3, rejected_count: 1 }),
      ],
    })
    renderAt('/profile/sources')

    expect(await screen.findByText('resume.pdf')).toBeInTheDocument()
    expect(screen.getByText('Pending 2')).toBeInTheDocument()
    expect(screen.getByText('Accepted 3')).toBeInTheDocument()
    expect(screen.getByText('Rejected 1')).toBeInTheDocument()
    expect(screen.getByText(/12 KB/)).toBeInTheDocument()
    expect(screen.getByText(/synthetic-parser v1\.0\.0/)).toBeInTheDocument()
  })

  it('uploads a resume and shows its pending facts', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/profile/sources': () => [],
      'POST /api/profile/sources': () =>
        json(
          profileSourceDetail({
            facts: [importedFact({ id: 'fact-a', name: 'Python', category: 'skill' })],
          }),
          201,
        ),
    })
    renderAt('/profile/sources')
    await screen.findByText('No files uploaded yet.')

    const input = screen.getByLabelText('Upload a resume') as HTMLInputElement
    const file = makeFile('resume.pdf', 'application/pdf', 1024)
    Object.defineProperty(input, 'files', { value: [file] })
    fireEvent.change(input)
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }))

    expect(
      await screen.findByText('Uploaded. 1 imported fact waiting for review.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Python')).toBeInTheDocument()
    expect(screen.getByText('Pending')).toBeInTheDocument()
    expect(screen.getByText('Imported')).toBeInTheDocument()

    const upload = calls.find((c) => c.method === 'POST')!
    expect(upload.headers['X-CSRF-Token']).toBe('synthetic-csrf')
    expect(upload.headers['Content-Type']).toBeUndefined()
    expect(upload.body).toBeInstanceOf(FormData)
    expect((upload.body as FormData).get('file')).toBe(file)
  })

  it('blocks an oversized file before sending a request', async () => {
    const calls = mockApi({ ...loggedIn, 'GET /api/profile/sources': () => [] })
    renderAt('/profile/sources')
    await screen.findByText('No files uploaded yet.')

    const input = screen.getByLabelText('Upload a resume') as HTMLInputElement
    const file = makeFile('huge.pdf', 'application/pdf', 3 * 1024 * 1024)
    Object.defineProperty(input, 'files', { value: [file] })
    fireEvent.change(input)
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }))

    expect(await screen.findByText(/larger than 2 MB/)).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
  })

  it('shows the server error detail for a rejected upload', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/profile/sources': () => [],
      'POST /api/profile/sources': () =>
        json({ detail: 'Only text and PDF resumes are supported.' }, 415),
    })
    renderAt('/profile/sources')
    await screen.findByText('No files uploaded yet.')

    const input = screen.getByLabelText('Upload a resume') as HTMLInputElement
    const file = makeFile('resume.docx', 'application/msword', 1024)
    Object.defineProperty(input, 'files', { value: [file] })
    fireEvent.change(input)
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Only text and PDF resumes are supported.',
    )
  })

  it('stages accept/reject/edit changes and applies them in one request', async () => {
    const detail = profileSourceDetail({
      facts: [
        importedFact({ id: 'fact-skill', name: 'Python', category: 'skill' }),
        importedFact({
          id: 'fact-project',
          name: 'Robotics club project',
          category: 'project',
          description: 'Built a line-following robot.',
        }),
      ],
    })
    const calls = mockApi({
      ...loggedIn,
      'GET /api/profile/sources': () => [profileSource()],
      'GET /api/profile/sources/psrc-1': () => detail,
      'POST /api/profile/sources/psrc-1/review': () =>
        json({
          source: profileSourceDetail({
            facts: [
              importedFact({ id: 'fact-skill', name: 'Py', review_state: 'accepted' }),
              importedFact({
                id: 'fact-project',
                name: 'Robotics club project',
                category: 'project',
                review_state: 'rejected',
              }),
            ],
          }),
          catalog_pass: true,
          evaluated_opportunities: 4,
          unchanged_opportunities: 1,
        }),
    })
    renderAt('/profile/sources')

    fireEvent.click(await screen.findByRole('button', { name: 'View facts' }))
    await screen.findByText('Python')

    fireEvent.click(screen.getAllByRole('button', { name: 'Accept' })[0])
    fireEvent.change(screen.getByLabelText('Name (Python)'), { target: { value: 'Py' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Reject' })[1])

    fireEvent.click(screen.getByRole('button', { name: 'Apply 2 changes' }))

    expect(
      await screen.findByText(
        'Scoring refreshed: 4 opportunities re-scored, 1 unchanged.',
      ),
    ).toBeInTheDocument()

    const review = calls.find((c) => c.method === 'POST')!
    expect(review.path).toBe('/api/profile/sources/psrc-1/review')
    expect(review.body).toEqual({
      accept: [{ id: 'fact-skill', name: 'Py' }],
      reject: ['fact-project'],
    })
  })

  it('shows "Saved. Matching unchanged." when the catalog is unaffected', async () => {
    const detail = profileSourceDetail()
    mockApi({
      ...loggedIn,
      'GET /api/profile/sources': () => [profileSource()],
      'GET /api/profile/sources/psrc-1': () => detail,
      'POST /api/profile/sources/psrc-1/review': () =>
        json({
          source: profileSourceDetail({
            facts: [importedFact({ review_state: 'accepted' })],
          }),
          catalog_pass: false,
          evaluated_opportunities: 0,
          unchanged_opportunities: 0,
        }),
    })
    renderAt('/profile/sources')

    fireEvent.click(await screen.findByRole('button', { name: 'View facts' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Accept' }))
    fireEvent.click(screen.getByRole('button', { name: 'Apply 1 change' }))

    expect(await screen.findByText('Saved. Matching unchanged.')).toBeInTheDocument()
  })

  it('deletes a file after confirmation', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const calls = mockApi({
      ...loggedIn,
      'GET /api/profile/sources': () => [profileSource()],
      'DELETE /api/profile/sources/psrc-1': () =>
        json({
          catalog_pass: false,
          evaluated_opportunities: 0,
          unchanged_opportunities: 0,
        }),
    })
    renderAt('/profile/sources')

    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
    expect(confirmSpy).toHaveBeenCalled()
    expect(screen.queryByText('resume.pdf')).not.toBeInTheDocument()
    confirmSpy.mockRestore()
  })

  it('does not delete when the confirmation is dismissed', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const calls = mockApi({
      ...loggedIn,
      'GET /api/profile/sources': () => [profileSource()],
    })
    renderAt('/profile/sources')

    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))

    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
    expect(screen.getByText('resume.pdf')).toBeInTheDocument()
    confirmSpy.mockRestore()
  })

  it('rejects a malformed server response via zod', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/profile/sources': () => [{ id: 'bad' }],
    })
    renderAt('/profile/sources')

    expect(
      await screen.findByText('The server sent an unexpected response.'),
    ).toBeInTheDocument()
  })

  it('never renders raw JSON for a fact', async () => {
    const detail = profileSourceDetail({
      facts: [importedFact({ description: 'A <b>bold</b> description with "quotes".' })],
    })
    mockApi({
      ...loggedIn,
      'GET /api/profile/sources': () => [profileSource()],
      'GET /api/profile/sources/psrc-1': () => detail,
    })
    renderAt('/profile/sources')

    fireEvent.click(await screen.findByRole('button', { name: 'View facts' }))

    const description = await screen.findByText(/A <b>bold<\/b> description/)
    expect(description.innerHTML).not.toContain('<b>')
    expect(document.body.innerHTML).not.toMatch(/"id"\s*:/)
  })

  it('shows the Sources tab on the profile pages', async () => {
    mockApi({ ...loggedIn, 'GET /api/profile/sources': () => [] })
    renderAt('/profile/sources')

    const tabs = await screen.findByRole('navigation', { name: 'Profile sections' })
    expect(within(tabs).getByRole('link', { name: 'Sources' })).toBeInTheDocument()
    expect(
      within(tabs).getByRole('link', { name: 'Eligibility Profile' }),
    ).toBeInTheDocument()
    expect(within(tabs).getByRole('link', { name: 'Match Profile' })).toBeInTheDocument()
  })
})
