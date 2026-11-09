/**
 * T-M12-02 — restaurant list renders, search input wired (FE-06).
 * (FE-14 loading/error states are covered in routing.test.jsx.)
 */
import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { renderPage } from '../../test/harness.jsx'
import { mockApi } from '../../test/mockApi.js'
import { restaurant, restaurantTwo } from '../../test/factories.js'
import Restaurants from '../Restaurants.jsx'

describe('Restaurants page', () => {
  it('renders the catalog with fees formatted from cents (T-M12-02)', async () => {
    mockApi([
      ['GET', '/restaurants', { items: [restaurant, restaurantTwo], total: 2, limit: 100, offset: 0 }],
    ])
    renderPage(Restaurants, { route: '/restaurants' })

    // The list loads asynchronously: wait for the first card, then assert the rest.
    await screen.findByText('Alpha')
    expect(screen.getByText('Beta')).toBeInTheDocument()
    expect(screen.getByText(/€2.50/)).toBeInTheDocument() // 250 cents, display only
    expect(screen.getByText(/€3.50/)).toBeInTheDocument() // 350 cents
  })

  it('sends no Authorization header for the public catalog (D16)', async () => {
    const { calls } = mockApi([
      ['GET', '/restaurants', { items: [restaurant], total: 1, limit: 100, offset: 0 }],
    ])
    renderPage(Restaurants, { route: '/restaurants' })
    await screen.findByText('Alpha')
    expect(calls[0].headers.Authorization).toBeUndefined()
  })

  it('filters the loaded list client-side by name (FE-06 search box)', async () => {
    mockApi([
      ['GET', '/restaurants', { items: [restaurant, restaurantTwo], total: 2, limit: 100, offset: 0 }],
    ])
    const user = userEvent.setup()
    renderPage(Restaurants, { route: '/restaurants' })
    await screen.findByText('Alpha')

    await user.type(screen.getByLabelText(/search by name/i), 'beta')
    expect(screen.queryByText('Alpha')).not.toBeInTheDocument()
    expect(screen.getByText('Beta')).toBeInTheDocument()
  })

  it('shows an empty state when nothing matches', async () => {
    mockApi([
      ['GET', '/restaurants', { items: [restaurant], total: 1, limit: 100, offset: 0 }],
    ])
    const user = userEvent.setup()
    renderPage(Restaurants, { route: '/restaurants' })
    await screen.findByText('Alpha')

    await user.type(screen.getByLabelText(/search by name/i), 'zzz-nothing')
    expect(await screen.findByText(/no restaurants match/i)).toBeInTheDocument()
  })

  it('links each card to its menu', async () => {
    mockApi([
      ['GET', '/restaurants', { items: [restaurant], total: 1, limit: 100, offset: 0 }],
    ])
    renderPage(Restaurants, { route: '/restaurants' })
    const link = await screen.findByRole('link', { name: /view menu/i })
    expect(link).toHaveAttribute('href', '/restaurants/1')
  })
})
