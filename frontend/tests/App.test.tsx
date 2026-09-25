import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from '../src/App'

function stubFetch(impl: () => Promise<Response>) {
  const fetchMock = vi.fn(impl)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

describe('App', () => {
  it('renders the app name and a loading state', () => {
    stubFetch(() => new Promise<Response>(() => {}))
    render(<App />)
    expect(
      screen.getByRole('heading', { name: 'Personal Internship Finder' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Checking…')
  })

  it('shows healthy when the backend reports ok', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(jsonResponse({ status: 'ok' })))
    render(<App />)
    expect(await screen.findByText('Healthy')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/health',
      expect.anything(),
    )
  })

  it('shows an error when the backend is unreachable', async () => {
    stubFetch(() => Promise.reject(new TypeError('Failed to fetch')))
    render(<App />)
    expect(await screen.findByText('Unavailable')).toBeInTheDocument()
    expect(screen.getByText('Failed to fetch')).toBeInTheDocument()
  })

  it('shows an error on a non-2xx response', async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ detail: 'boom' }, 500)))
    render(<App />)
    expect(await screen.findByText('Health check failed (HTTP 500)')).toBeInTheDocument()
  })

  it.each([
    ['wrong status value', () => jsonResponse({ status: 'degraded' })],
    ['missing field', () => jsonResponse({})],
    ['non-JSON body', () => new Response('<html>oops</html>', { status: 200 })],
  ])('handles a malformed health response safely (%s)', async (_label, makeResponse) => {
    stubFetch(() => Promise.resolve(makeResponse()))
    render(<App />)
    expect(await screen.findByText('Unavailable')).toBeInTheDocument()
    expect(
      screen.getByText('Backend returned an unexpected health response'),
    ).toBeInTheDocument()
  })
})
